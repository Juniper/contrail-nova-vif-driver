# Derived from github.com:Juniper/nova/virt/libvirt/vif.py licenced under the
# Apache Licence, Version 2.0. Please see there for the copyright details.
#
# Copyright 2016 Semihalf.
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

import socket

from os_vif import objects
from os_vif import plugin

from oslo_config import cfg
from oslo_concurrency import processutils
from oslo_log import log as logging

from vif_plug_vrouter import exception
from vif_plug_vrouter.i18n import _LE
from vif_plug_vrouter import privsep

LOG = logging.getLogger(__name__)

@privsep.vif_plug.entrypoint
def run_vrouter_port_control(args):
    try:
        processutils.execute("vrouter-port-control", args)
    except Exception as e:
        LOG.error(_LE("Unable to execute vrouter-port-control " +
                      "%(args)s.  Exception: %(exception)s"),
                  {'args': args, 'exception': e})
        raise exception.VrouterPortControlError(args=args)

class VrouterPlugin(plugin.PluginBase):
    """A vRouter plugin that can setup VIFs in both kernel and vhostuser mode.

    TODO: Add more detailed description.
    """

    def describe(self):
        return objects.host_info.HostPluginInfo(
            plugin_name="vrouter",
            vif_info=[
                objects.host_info.HostVIFInfo(
                    vif_object_name=objects.vif.VIFVHostUser.__name__,
                    min_version="1.0",
                    max_version="1.0")
            ])

    @staticmethod
    def _vrouter_port_add(instance_info, vif):
        ip_addr = '0.0.0.0'
        ip6_addr = None
        subnets = vif.network.subnets
        for subnet in subnets:
            if not hasattr(subnet, 'ips'):
                continue
            ip = subnet.ips[0]
            if not ip.address:
                continue
            if ip.address.version == 4:
                if ip.address is not None:
                    ip_addr = ip.address
            if ip.address.version == 6:
                if ip.address is not None:
                    ip6_addr = ip.address

        ptype = 'NovaVMPort'
        if (cfg.CONF.libvirt.virt_type == 'lxc'):
            ptype = 'NameSpacePort'

        vif_type = 'Vrouter'
        vhostuser_socket = ''
        if isinstance(vif, objects.vif.VIFVHostUser):
            vif_type = 'VhostUser'
            vhostuser_socket = ' --vhostuser_socket=%s' % vif.path

        cmd_args = ("--oper=add --uuid=%s --instance_uuid=%s --vn_uuid=%s "
                    "--vm_project_uuid=%s --ip_address=%s --ipv6_address=%s"
                    " --vm_name=%s --mac=%s --tap_name=%s --port_type=%s "
                    "--vif_type=%s%s --tx_vlan_id=%d --rx_vlan_id=%d" %
                    (vif.id, instance_info.uuid, vif.network.id,
                    instance_info.project_id, ip_addr, ip6_addr,
                    instance_info.name, vif.address,
                    vif.vif_name, ptype, vif_type, vhostuser_socket, -1, -1))

        run_vrouter_port_control(cmd_args)

    def plug(self, vif, instance_info):
        if not (isinstance(vif, objects.vif.VIFVHostUser) or
                isinstance(vif, objects.vif.VIFGeneric)):
            raise exception.VrouterUnknownVIFError(id=vif.id)

        self._vrouter_port_add(instance_info, vif)

    @staticmethod
    def _vrouter_port_delete(instance_info, vif):
        cmd_args = ("--oper=delete --uuid=%s" % (vif.id))
        run_vrouter_port_control(cmd_args)

    def unplug(self, vif, instance_info):
        if not (isinstance(vif, objects.vif.VIFVHostUser) or
                isinstance(vif, objects.vif.VIFGeneric)):
            raise exception.VrouterUnknownVIFError(id=vif.id)

        self._vrouter_port_delete(instance_info, vif)
