#!/usr/bin/python env

import io
import os, sys, getopt
import subprocess
import docker
import shutil
import re

# docker connect

client = docker.DockerClient(base_url='unix://var/run/docker.sock')

# set options and variables

try:
    options, remainder = getopt.getopt(sys.argv[1:], 't:s', ['tag=', 'service='])

    for opt, arg in options:
        if opt in ('-t', '--tag'):
            tag = arg.lower()
        if opt in ('-s', '--service'):
            service = arg

    src = '/var/containers/project/templates'
    registry = 'registry.domain.com/project/repo-'
    project = ['web', 'app', 'crm', 'payments', 'postbacks', 'raw', 'stat', 'tds', 'landings']
    container_dir = '/var/containers/project/%s' % tag
    branch_config = '/etc/nginx/conf.d/project/%s.conf' % tag
    values = []
    docker_port = []
    disable_migrations = ['web']
    env = tag

except (getopt.GetoptError, NameError) as err:
    help_string = "Usage:\n./%s --tag <branch number> --service <project name>" % sys.argv[0]
    print(help_string)
    sys.exit(2)

# functions

def workdir(src, container_dir, symlinks=False, ignore=None):

    if not os.path.exists(container_dir):
        os.mkdir(container_dir)

    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(container_dir, item)
        if os.path.isfile(s):
            shutil.copyfile(s, d)
        elif os.path.exists(d):
            shutil.rmtree(d)
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copytree(s, d, symlinks, ignore)

def sync_image(tag, container_dir):

    for image in project[:-1]:
        proc = subprocess.Popen(['DOCKER_CLI_EXPERIMENTAL=enabled docker manifest inspect registry.domain.com/project/repo-%s:%s &>/dev/null; echo $?' \
                                 % (image, tag)], shell=True, stdout=subprocess.PIPE)
        for line in io.TextIOWrapper(proc.stdout, encoding="utf-8"):
            value = str(line.rstrip())
            values.append(value)

    dict = {key: value for key, value in zip(project, values)}
    for k, v in dict.items():
        v = v.replace('0', ':%s' % tag)
        v = v.replace('1', ':stage')
        pull = registry + k + v
        image = client.images.pull(pull)
        if pull.endswith('stage'):
            image.tag(pull, tag=tag)

    with open('%s/.env' % container_dir, 'w') as branch:
        branch.write('TAG=%s' % tag)
        branch.close

def deploy_and_migrations(container_dir, service, tag):

    for container in client.containers.list(all=True, filters={"name": service + "_%s" % tag }):
        container.remove(force=True)
        print('Container: %s' % container.name + " removed.")

    deploy = subprocess.Popen(['docker-compose up -d --build --remove-orphans'], shell=True, cwd=container_dir, stdout=subprocess.PIPE)
    for line in io.TextIOWrapper(deploy.stdout, encoding="utf-8"):
        status = str(line.rstrip())
        print(status)

    for docker in project[:-1]:
        for container in client.containers.list(all=True, filters={"name": "project_%s_%s" % (docker, tag), "status": "running" }):
            container.exec_run(cmd='chmod -R 0777 /code/var', user='root', stdout=True)
            if not container.name.startswith(str(disable_migrations[0])):
                create_database = container.exec_run(cmd='/code/bin/console doctrine:database:create --if-not-exists', user='www-data', stdout=True)
                migrations = container.exec_run(cmd='/code/bin/console doctrine:migrations:migrate -n', user='www-data', stdout=True)
                logger = [create_database, migrations]
                for logs in logger:
                    print(logs.decode("utf-8"))

def nginx_for_branch(branch_config, tag, src):

    with open(branch_config, 'w+') as raw:
        raw.read().split("\n")
        raw.seek(0)
        raw.truncate()

    for service_port in project:
        container_name = "project_%s_%s" % (service_port, tag)
        deploy = subprocess.Popen(['docker port %s 80' % container_name], shell=True, stdout=subprocess.PIPE)
        for line in io.TextIOWrapper(deploy.stdout, encoding="utf-8"):
            proxy_pass = str(line.rstrip())
            docker_port.append(proxy_pass)

    for (nginx_config, nginx_port) in zip(project, docker_port):
        with open("%s/nginx_branch.conf" % src, 'rt') as f:
            one = f.read()
            data = one.replace('template.domain.com', "%s-%s.project.domain.com" % (tag, nginx_config))
            data = data.replace('template.access.log', "%s_%s.access.log" % (tag, nginx_config))
            data = data.replace('template.error.log', "%s_%s.error.log" % (tag, nginx_config))
            data = data.replace('template_docker_port', "http://%s" % nginx_port)
            f.close()
        with open(branch_config, 'a+') as w:
            w.write(data)
            w.close

    try:
        nginx_check = subprocess.check_output(['nginx', '-t'], stderr=subprocess.STDOUT)
        for check in nginx_check.splitlines():
            status = check.decode("utf-8")
            if re.search('successful', status):
                subprocess.call('nginx -s reload', shell=True)
    except subprocess.CalledProcessError as e:
        error = "command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output.decode('utf-8'))
        print(error)


if __name__ == '__main__':
    if env == 'stage' or env == 'master':
        deploy_and_migrations(container_dir='/var/containers/project', service=service, tag=tag)
    else:
        env = 'dev'
        workdir(src, container_dir, symlinks=False, ignore=None)
        sync_image(tag, container_dir)
        deploy_and_migrations(container_dir, service, tag)
        nginx_for_branch(branch_config, tag, src)
