# Copyright (C) 2017 Netronome Systems, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from os_vif import objects
from vif_plug_vrouter import vrouter


class VrouterPlugin(vrouter.VrouterPlugin):
    """A vRouter os-vif plugin for vhostuser type VIF's

    This class is a small shim that unifies the 'vrouter' and
    'contrail_vrouter' VIF types.
    """

    def describe(self):
        return objects.host_info.HostPluginInfo(
            plugin_name="contrail_vrouter",
            vif_info=[
                objects.host_info.HostVIFInfo(
                    vif_object_name=objects.vif.VIFVHostUser.__name__,
                    min_version="1.0",
                    max_version="1.0"),

            ])
