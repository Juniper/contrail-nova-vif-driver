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

import os
from os_vif import objects
from os_vif import plugin

from oslo_concurrency import processutils
from oslo_config import cfg
from oslo_log import log as logging

from vif_plug_vrouter import exception
from vif_plug_vrouter.i18n import _LE
from vif_plug_vrouter import privsep

LOG = logging.getLogger(__name__)
VHOSTUSER_MODE_SERVER = 1
VHOSTUSER_MODE_CLIENT = 0


@privsep.vif_plug.entrypoint
def plug_contrail_vif(vif_id, vm_id, net_id, project_id, ip_addr, ip6_addr,
                      vm_name, mac, dev_name, port_type, vif_type=None,
                      vnic_type=None, pci_dev=None, vhostuser_socket=None,
                      vhostuser_mode=None):
    """Call the vrouter port control script to plug a VIF

    :param vif_id: VIF ID to plug
    :param vm_id: Instance ID
    :param net_id: Network ID
    :param project_id: Project ID associated with the instance
    :param ip_addr: IPv4 address to assign to the interface
    :param ip6_addr: IPv6 address to assign to the interface
    :param vm_name: Display name of the instance
    :param mac: MAC address to assign to the interface
    :param dev_name: Name of the TAP/device to plug
    :param port_type: vrouter port type (e.g. NovaVMPort)
    :param vif_type: vrouter VIF type (e.g. VhostUser)
    :param vnic_type: Selector for offload mode (e.g. direct)
    :param pci_dev: Virtual Function to assign for offloading
    :param vhostuser_socket: vhost-user socket path
    :param vhostuser_mode: vhost-user mode (client/server)
    """
    cmd = (
        'vrouter-port-control',
        '--oper=add',
        '--uuid=%s' % vif_id,
        '--instance_uuid=%s' % vm_id,
        '--vn_uuid=%s' % net_id,
        '--vm_project_uuid=%s' % project_id,
        '--ip_address=%s' % ip_addr,
        '--ipv6_address=%s' % ip6_addr,
        '--vm_name=%s' % vm_name,
        '--mac=%s' % mac,
        '--tap_name=%s' % dev_name,
        '--port_type=%s' % port_type,
    )
    if vif_type:
        cmd += ('--vif_type=%s' % vif_type,)
    if vnic_type:
        cmd += ('--vnic_type=%s' % vnic_type,)
    if pci_dev:
        cmd += ('--pci_dev=%s' % pci_dev,)
    if vhostuser_socket:
        cmd += ('--vhostuser_socket=%s' % vhostuser_socket,)
    if vhostuser_mode is not None:
        cmd += ('--vhostuser_mode=%s' % vhostuser_mode,)
    cmd += (
        '--tx_vlan_id=%d' % -1,
        '--rx_vlan_id=%d' % -1,
    )
    try:
        env = dict(os.environ)
        env['PATH'] = env['PATH'] + ':/opt/plugin/bin'
        processutils.execute(*cmd, env_variables=env)
    except Exception as e:
        LOG.error(_LE("Unable to execute vrouter-port-control "
                      "%(args)s.  Exception: %(exception)s"),
                  {'args': cmd, 'exception': e})
        raise exception.VrouterPortControlError(args=cmd)


@privsep.vif_plug.entrypoint
def unplug_contrail_vif(port_id, dev_name=None, vnic_type=None, pci_dev=None,
                        vhostuser_socket=None, vhostuser_mode=None):
    """Call the vrouter port control script to unplug a vif

    :param port_id: VIF ID to unplug
    :param dev_name: Name of the TAP/device to unplug
    :param vnic_type: Selector for offload mode (e.g. direct)
    :param pci_dev: Virtual Function to assign for offloading
    :param vhostuser_socket: vhost-user socket path
    :param vhostuser_mode: vhost-user mode (client/server)
    """
    cmd = (
        'vrouter-port-control',
        '--oper=delete',
        '--uuid=%s' % port_id,
    )
    if dev_name:
        cmd += ('--tap_name=%s' % dev_name,)
    if vnic_type:
        cmd += ('--vnic_type=%s' % vnic_type,)
    if pci_dev:
        cmd += ('--pci_dev=%s' % pci_dev,)
    if vhostuser_socket:
        cmd += ('--vhostuser_socket=%s' % vhostuser_socket,)
    if vhostuser_mode is not None:
        cmd += ('--vhostuser_mode=%s' % vhostuser_mode,)
    try:
        env = dict(os.environ)
        env['PATH'] = env['PATH'] + ':/opt/plugin/bin'
        processutils.execute(*cmd, env_variables=env)
    except Exception as e:
        LOG.error(_LE("Unable to execute vrouter-port-control "
                      "%(args)s.  Exception: %(exception)s"),
                  {'args': cmd, 'exception': e})
        raise exception.VrouterPortControlError(args=cmd)


class VrouterPlugin(plugin.PluginBase):
    """An os-vif plugin that can setup vrouter VIFs in both kernel and
       dpdk vhostuser mode.

    This is the unified os-vif plugin for the following OS-VIF plugging modes:

      * DPDK vhost-user plugging (VIFVHostUser)
      * Classic kernel plugging (vrouter.ko) via TAP device (VIFGeneric)
        * direct offloaded kernel datapath (VIFHostDevice)
        * indirect offloaded kernel datapath (VIFVHostUser)

    This plugin gets called by Nova to plug the VIFs into and unplug them from
    the datapath. There is corresponding code in Nova to configure the
    hypervisor configure the VM to connect to the required connection method.
    """

    def describe(self):
        if 'supported_port_profiles' in objects.host_info.HostVIFInfo.fields:
            pp = objects.host_info.HostPortProfileInfo(
                profile_object_name=
                objects.vif.VIFPortProfileBase.__name__,
                min_version="1.0",
                max_version="1.1"
            )
            return objects.host_info.HostPluginInfo(
                plugin_name="vrouter",
                vif_info=[
                    objects.host_info.HostVIFInfo(
                        vif_object_name=objects.vif.VIFGeneric.__name__,
                        min_version="1.0",
                        max_version="1.0",
                        supported_port_profiles=[pp]),
                    objects.host_info.HostVIFInfo(
                        vif_object_name=objects.vif.VIFVHostUser.__name__,
                        min_version="1.0",
                        max_version="1.1",
                        supported_port_profiles=[pp]),
                    objects.host_info.HostVIFInfo(
                        vif_object_name=objects.vif.VIFHostDevice.__name__,
                        min_version="1.0",
                        max_version="1.0",
                        supported_port_profiles=[pp])
                ])
        else:
            # Older versions of os-vif did not feature supported_port_profiles
            return objects.host_info.HostPluginInfo(
                plugin_name="vrouter",
                vif_info=[
                    objects.host_info.HostVIFInfo(
                        vif_object_name=objects.vif.VIFGeneric.__name__,
                        min_version="1.0",
                        max_version="1.0"),
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
            if ('ips' not in subnet or
                not hasattr(subnet, 'ips')):
                continue
            ip = subnet.ips[0]
            if not ip.address:
                continue
            if ip.address.version == 4:
                if ip.address is not None:
                    ip_addr = str(ip.address)
            if ip.address.version == 6:
                if ip.address is not None:
                    ip6_addr = str(ip.address)

        try:
            virt_type = cfg.CONF.libvirt.virt_type
        except cfg.NoSuchOptError:
            try:
                virt_type = cfg.CONF.libvirt_type
            except cfg.NoSuchOptError:
                virt_type = None

        ptype = 'NovaVMPort'
        if (virt_type == 'lxc'):
            ptype = 'NameSpacePort'

        vif_type = None
        vhostuser_socket = None
        vhostuser_mode = None
        vnic_type = None
        pci_dev = None

        if isinstance(vif, objects.vif.VIFVHostUser):
            vif_type = 'VhostUser'
            vhostuser_socket = vif.path
            if vif.mode == 'server':
                vhostuser_mode = VHOSTUSER_MODE_SERVER
            else:
                vhostuser_mode = VHOSTUSER_MODE_CLIENT

        if ('port_profile' in vif and
            hasattr(vif, 'port_profile') and
            isinstance(vif.port_profile, objects.vif.VIFPortProfileBase)):
            if ('datapath_offload' in vif.port_profile and
                hasattr(vif.port_profile, 'datapath_offload') and
                isinstance(vif.port_profile.datapath_offload,
                           objects.vif.DatapathOffloadRepresentor)):
                if isinstance(vif, objects.vif.VIFVHostUser):
                    vnic_type = 'virtio-forwarder'
                elif isinstance(vif, objects.vif.VIFHostDevice):
                    vnic_type = 'direct'
                pci_dev = vif.port_profile.datapath_offload.representor_address

        plug_contrail_vif(vif.id, instance_info.uuid, vif.network.id,
                          instance_info.project_id, ip_addr, ip6_addr,
                          instance_info.name, vif.address,
                          vif.vif_name, ptype, vif_type, vnic_type, pci_dev,
                          vhostuser_socket, vhostuser_mode)

    def plug(self, vif, instance_info):
        if not (isinstance(vif, objects.vif.VIFVHostUser) or
                isinstance(vif, objects.vif.VIFGeneric) or
                isinstance(vif, objects.vif.VIFHostDevice)):
            raise exception.VrouterUnknownVIFError(id=vif.id)

        self._vrouter_port_add(instance_info, vif)

    @staticmethod
    def _vrouter_port_delete(instance_info, vif):
        vhostuser_socket = None
        vhostuser_mode = None
        vnic_type = None
        pci_dev = None
        dev_name = None

        if ('port_profile' in vif and
            hasattr(vif, 'port_profile') and
            isinstance(vif.port_profile, objects.vif.VIFPortProfileBase)):
            if ('datapath_offload' in vif.port_profile and
                hasattr(vif.port_profile, 'datapath_offload') and
                isinstance(vif.port_profile.datapath_offload,
                           objects.vif.DatapathOffloadRepresentor)):
                if isinstance(vif, objects.vif.VIFVHostUser):
                    vnic_type = 'virtio-forwarder'
                    vhostuser_socket = vif.path
                    dev_name = vif.vif_name
                    if vif.mode == 'server':
                        vhostuser_mode = VHOSTUSER_MODE_SERVER
                    else:
                        vhostuser_mode = VHOSTUSER_MODE_CLIENT
                elif isinstance(vif, objects.vif.VIFHostDevice):
                    vnic_type = 'direct'
                pci_dev = vif.port_profile.datapath_offload.representor_address

        unplug_contrail_vif(vif.id, dev_name, vnic_type, pci_dev,
                            vhostuser_socket, vhostuser_mode)

    def unplug(self, vif, instance_info):
        if not (isinstance(vif, objects.vif.VIFVHostUser) or
                isinstance(vif, objects.vif.VIFGeneric) or
                isinstance(vif, objects.vif.VIFHostDevice)):
            raise exception.VrouterUnknownVIFError(id=vif.id)

        self._vrouter_port_delete(instance_info, vif)
