#!/usr/bin/env python3

import requests
import json
import os
import re
import yaml
import glob
from dotenv import load_dotenv
from pathlib import Path
from git import Repo
from git.remote import RemoteProgress

dotenv_path = Path('.env')
load_dotenv()


class DevOpsScript:
    def __init__(self):
        self.registry = os.getenv('ENDPOINT')
        self.creds = os.getenv('AUTH')
        self.auth = {'Content-Type': 'application/json', 'Authorization': 'Basic %s' % self.creds}
        self.params = {'n': 5000}
        self.regex_image_name = '(?:\w+\.\w+\.\w+\/)?([^:]+)(?::.+)?'
        self.regex_docker_tag = '((?P<tag>[\w.\-_]{1,127})|)$'
        self.extensions = ['*.yml', '*.yaml']
        self.depth = ['*', '*/*']
        self.registry_array = self.get_repos_with_tags(self.registry, self.auth, self.params)
        self.prod_array = self.join_dict_to_dict()

    class Progress(RemoteProgress):
        def line_dropped(self, line):
            print(line)

        def update(self, *args):
            print(self._cur_line)

    def pull_repo(self):
        with open('info.yaml', "r") as stream:
            vars_yaml = yaml.safe_load(stream)
            for git_folders, private_keys in zip(vars_yaml['vars']['folders'], vars_yaml['vars']['keys']):
                repo = Repo(git_folders)
                with repo.git.custom_environment(GIT_SSH_COMMAND=private_keys):
                    repo.remotes.origin.pull(progress=self.Progress())

    def k8s_yaml_parser(self, deployment):
        parsed = {}
        if os.path.isfile(deployment):
            with open(deployment, "r") as stream:
                deployment = yaml.safe_load(stream)
                for get_image in deployment['spec']['template']['spec']['containers']:
                    try:
                        image = get_image['image']
                        for image_name, docker_tag in zip(re.findall(self.regex_image_name, image),
                                                          re.findall(self.regex_docker_tag, image)):
                            parsed[image_name] = docker_tag[0]
                    except:
                        continue
        return parsed

    @staticmethod
    def docker_yaml_parser(deployment):
        parsed = {}
        if os.path.isfile(deployment):
            with open(deployment, "r") as stream:
                deployment = yaml.safe_load(stream)
                services = deployment if isinstance(deployment, list) else deployment.get('services', [])
                for get_image in services:
                    try:
                        image = get_image.get('image', '')
                        for image_name, docker_tag in zip(re.findall(DevOpsScript.regex_image_name, image),
                                                          re.findall(DevOpsScript.regex_docker_tag, image)):
                            parsed[image_name] = docker_tag[0]
                    except:
                        continue
        return parsed

    def output_manifests(self, type_instance):
        docker_compose_files = []
        for all_yaml in self.depth:
            for project_dir in glob.glob(os.path.join(type_instance, all_yaml)):
                files = [f for ext in self.extensions for f in glob.glob(os.path.join(project_dir, ext))]
                for list_compose_files in files:
                    docker_compose_files.append(list_compose_files)
        return docker_compose_files

    def output_manifests_kubernetes(self, type_instance):
        kubernetes_files = []
        for deployments in os.listdir('%s/services' % type_instance):
            kubernetes_files.append('%s/services/%s/deployment.yaml' % (type_instance, deployments))
        return kubernetes_files

    def join_dict_to_dict(self):
        k8s_dict = {}
        vars_yaml = yaml.safe_load(open('info.yaml', "r"))
        for kubernetes_manifests in self.output_manifests_kubernetes(vars_yaml['vars']['folders'][0]):
            if kubernetes_manifests not in vars_yaml['vars']['exclude_list']:
                for k8s_image, k8s_tag in self.k8s_yaml_parser(kubernetes_manifests).items():
                    k8s_dict[k8s_image] = k8s_tag
        docker_dict = {}
        for docker_manifests in self.output_manifests(vars_yaml['vars']['folders'][1]):
            if docker_manifests not in vars_yaml['vars']['exclude_list']:
                try:
                    for docker_image, docker_tag in DevOpsScript.docker_yaml_parser(docker_manifests).items():
                        docker_dict[docker_image] = docker_tag
                except KeyError:
                    continue
        main_dict = k8s_dict | docker_dict
        return main_dict

    @staticmethod
    def get_tags(url, repo, headers):
        params = {'orderby': 'timedesc'}
        with requests.get('https://%s/v2/%s/tags/list' % (url, repo), headers=headers, params=params) as data:
            answer = json.loads(data.text)
        return answer

    @staticmethod
    def get_repos_with_tags(registry, auth, params):
        repos = {}
        with requests.get('https://%s/acr/v1/_catalog' % registry, headers=auth, params=params) as data:
            answer = json.loads(data.text)
        for repo in answer['repositories']:
            repo_data = DevOpsScript.get_tags(registry, repo, auth)  # Зміна тут
            repos[repo_data['name']] = repo_data['tags']
        return repos

    def show_digests(self, url, repo_name, headers):
        with requests.get('https://%s/acr/v1/%s/_manifests' % (url, repo_name), headers=headers,
                          params=self.params) as data:
            answer = json.loads(data.text)
        return answer

    def remove_function(self, array_name, array_tag):
        for deleted_versions in array_tag:
            print('Will delete image: %s tag: %s' % (array_name, deleted_versions))
            self.delete_tags(self.registry, array_name, deleted_versions, self.auth)
        for digest in self.show_digests(self.registry, array_name, self.auth)['manifests']:
            try:
                print('Will stay image: %s with tag: %s' % (array_name, digest['tags']))
            except:
                print('Will delete untagged manifest: %s from image: %s' % (array_name, digest['digest']))
                self.delete_manifests(self.registry, array_name, digest['digest'], self.auth)

    def delete_tags(self, url, repo_name, repo_tag, headers):
        with requests.delete('https://%s/acr/v1/%s/_tags/%s' % (url, repo_name, repo_tag), headers=headers,
                             params=self.params) as data:
            answer = data.status_code
        return answer

    def delete_manifests(self, url, repo_name, digest, headers):
        with requests.delete('https://%s/v2/%s/manifests/%s' % (url, repo_name, digest), headers=headers,
                             params=self.params) as data:
            answer = data.status_code
        return answer


if __name__ == "__main__":
    script = DevOpsScript()
    script.pull_repo()
    clear_array = {}

    for prod_image, prod_version in script.prod_array.items():
        if prod_image in list(script.registry_array.keys()):
            del script.registry_array[prod_image][0:script.registry_array[prod_image].index(prod_version) + 1]
            clear_array[prod_image] = script.registry_array[prod_image]

    for name, tag in clear_array.items():
        script.remove_function(name, tag)
