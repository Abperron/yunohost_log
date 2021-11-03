# -*- coding: utf-8 -*-

""" License

    Copyright (C) 2021 YUNOHOST.ORG

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program; if not, see http://www.gnu.org/licenses

"""
import os
import copy
import psutil
from typing import Dict, Any

from yunohost.utils.error import YunohostError, YunohostValidationError
from yunohost.utils.filesystem import free_space_in_directory


class AppResource(object):

    def __init__(self, properties: Dict[str, Any], app_id: str):

        self.app_id = app_id

        for key, value in self.default_properties.items():
            setattr(self, key, value)

        for key, value in properties.items():
            setattr(self, key, value)

    def get_app_settings(self):
        from yunohost.app import _get_app_settings
        return _get_app_settings(self.app_id)

    def check_availability(self, context: Dict):
        pass


class AppResourceSet:

    def __init__(self, resources_dict: Dict[str, Dict[str, Any]], app_id: str):

        self.set = {name: AppResourceClassesByType[name](infos, app_id)
                    for name, infos in resources_dict.items()}

    def check_availability(self):

        for name, resource in self.set.items():
            resource.check_availability(context={})


M = 1024 ** 2
G = 1024 * M
sizes = {
    "10M": 10 * M,
    "20M": 20 * M,
    "40M": 40 * M,
    "80M": 80 * M,
    "100M": 100 * M,
    "200M": 200 * M,
    "400M": 400 * M,
    "800M": 800 * M,
    "1G": 1 * G,
    "2G": 2 * G,
    "4G": 4 * G,
    "8G": 8 * G,
    "10G": 10 * G,
    "20G": 20 * G,
    "40G": 40 * G,
    "80G": 80 * G,
}


class DiskAppResource(AppResource):
    type = "disk"

    default_properties = {
        "space": "10M",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # FIXME: better error handling
        assert self.space in sizes

    def assert_availability(self, context: Dict):

        if free_space_in_directory("/") <= sizes[self.space] \
        or free_space_in_directory("/var") <= sizes[self.space]:
            raise YunohostValidationError("Not enough disk space")  # FIXME: i18n / better messaging


class RamAppResource(AppResource):
    type = "ram"

    default_properties = {
        "build": "10M",
        "runtime": "10M",
        "include_swap": False
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # FIXME: better error handling
        assert self.build in sizes
        assert self.runtime in sizes
        assert isinstance(self.include_swap, bool)

    def assert_availability(self, context: Dict):

        memory = psutil.virtual_memory().available
        if self.include_swap:
            memory += psutil.swap_memory().available

        max_size = max(sizes[self.build], sizes[self.runtime])

        if memory <= max_size:
            raise YunohostValidationError("Not enough RAM/swap")  # FIXME: i18n / better messaging


class AptDependenciesAppResource(AppResource):
    type = "apt"

    default_properties = {
        "packages": [],
        "extras": {}
    }

    def check_availability(self, context):
        # ? FIXME
        # call helpers idk ...
        pass

class SourcesAppResource(AppResource):
    type = "sources"

    default_properties = {
        "main": {"url": "?", "sha256sum": "?", "predownload": True}
    }

    def check_availability(self, context):
        # ? FIXME
        # call request.head on the url idk
        pass


class RoutesAppResource(AppResource):
    type = "routes"

    default_properties = {
        "full_domain": False,
        "main": {
            "url": "/",
            "additional_urls": [],
            "init_allowed": "__FIXME__",
            "show_tile": True,
            "protected": False,
            "auth_header": True,
            "label": "FIXME",
        }
    }

    def check_availability(self, context):

        from yunohost.app import _assert_no_conflicting_apps

        app_settings = self.get_app_settings()
        domain = app_settings["domain"]
        path = app_settings["path"] if not self.full_domain else "/"
        _assert_no_conflicting_apps(domain, path, ignore_app=self.app_id)

    def provision_or_update(self, context: Dict):

        if context["app_action"] == "install":
            pass # FIXME
            # Initially, the .main permission is created with no url at all associated
            # When the app register/books its web url, we also add the url '/'
            # (meaning the root of the app, domain.tld/path/)
            # and enable the tile to the SSO, and both of this should match 95% of apps
            # For more specific cases, the app is free to change / add urls or disable
            # the tile using the permission helpers.
            #permission_create(
            #    self.app_id + ".main",
            #    allowed=["all_users"],
            #    label=label,
            #    show_tile=False,
            #    protected=False,
            #)
            #permission_url(app + ".main", url="/", sync_perm=False)
            #user_permission_update(app + ".main", show_tile=True, sync_perm=False)
            #permission_sync_to_user()

    def deprovision(self, context: Dict):
        del context["app_settings"]["domain"]
        del context["app_settings"]["path"]


class PortAppResource(AppResource):
    type = "port"

    default_properties = {
        "value": 1000
    }

    def _port_is_used(self, port):

        # FIXME : this could be less brutal than two os.system ...
        cmd1 = "ss --numeric --listening --tcp --udp | awk '{print$5}' | grep --quiet --extended-regexp ':%s$'" % port
        # This second command is mean to cover (most) case where an app is using a port yet ain't currently using it for some reason (typically service ain't up)
        cmd2 = f"grep -q \"port: '{port}'\" /etc/yunohost/apps/*/settings.yml"
        return os.system(cmd1) == 0 and os.system(cmd2) == 0

    def provision_or_update(self, context: str):

        # Don't do anything if port already defined ?
        if context["app_settings"].get("port"):
            return

        port = self.value
        while self._port_is_used(port):
            port += 1

        context["app_settings"]["port"] = port

    def deprovision(self, context: Dict):
        raise NotImplementedError()


class SystemuserAppResource(AppResource):
    type = "system_user"

    default_properties = {
        "username": "__APP__",
        "home_dir": "/var/www/__APP__",
        "use_shell": False,
        "groups": []
    }

    def check_availability(self, context):
        if os.system(f"getent passwd {self.username} &>/dev/null") != 0:
            raise YunohostValidationError(f"User {self.username} already exists")
        if os.system(f"getent group {self.username} &>/dev/null") != 0:
            raise YunohostValidationError(f"Group {self.username} already exists")

    def provision_or_update(self, context: str):
        raise NotImplementedError()

    def deprovision(self, context: Dict):
        raise NotImplementedError()


class InstalldirAppResource(AppResource):
    type = "install_dir"

    default_properties = {
        "dir": "/var/www/__APP__",    # FIXME or choose to move this elsewhere nowadays idk...
        "alias": "final_path"
    }

    # FIXME: change default dir to /opt/stuff if app ain't a webapp ...

    def check_availability(self, context):
        if os.path.exists(self.dir):
            raise YunohostValidationError(f"Folder {self.dir} already exists")

    def provision_or_update(self, context: Dict):

        if context["app_action"] in ["install", "restore"]:
            if os.path.exists(self.dir):
                raise YunohostValidationError(f"Path {self.dir} already exists")

        if "installdir" not in context["app_settings"]:
            context["app_settings"]["installdir"] = self.dir
        context["app_settings"][self.alias] = context["app_settings"]["installdir"]

    def deprovision(self, context: Dict):
        # FIXME: should it rm the directory during remove/deprovision ?
        pass


class DatadirAppResource(AppResource):
    type = "data_dir"

    default_properties = {
        "dir": "/home/yunohost.app/__APP__",    # FIXME or choose to move this elsewhere nowadays idk...
    }

    def check_availability(self, context):
        if os.path.exists(self.dir):
            raise YunohostValidationError(f"Folder {self.dir} already exists")

    def provision_or_update(self, context: Dict):
        if "datadir" not in context["app_settings"]:
            context["app_settings"]["datadir"] = self.dir

    def deprovision(self, context: Dict):
        # FIXME: should it rm the directory during remove/deprovision ?
        pass


class DBAppResource(AppResource):
    type = "db"

    default_properties = {
        "type": "mysql"
    }

    def check_availability(self, context):
        # FIXME : checking availability sort of imply that mysql / postgresql is installed
        # or we gotta make sure mariadb-server or postgresql is gonna be installed (apt resource)
        pass

    def provision_or_update(self, context: str):
        raise NotImplementedError()

    def deprovision(self, context: Dict):
        raise NotImplementedError()


AppResourceClassesByType = {c.type: c for c in AppResource.__subclasses__()}
