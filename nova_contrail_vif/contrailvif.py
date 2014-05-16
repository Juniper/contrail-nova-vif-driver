import gettext

gettext.install('contrail_vif')

from nova import exception
from nova.network import linux_net
from nova.openstack.common import log as logging
from nova.openstack.common import loopingcall
from nova.virt.libvirt import designer
from nova.virt.libvirt.vif import LibvirtBaseVIFDriver
from contrail_vrouter_api.vrouter_api import ContrailVRouterApi

LOG = logging.getLogger(__name__)


class VRouterVIFDriver(LibvirtBaseVIFDriver):
    """VIF driver for VRouter when running Quantum."""

    def __init__(self, get_connection):
        super(VRouterVIFDriver, self).__init__(get_connection)
        self._vrouter = ContrailVRouterApi()
        timer = loopingcall.FixedIntervalLoopingCall(
                  self._vrouter.periodic_connection_check)
        timer.start(interval=2)
    #end __init__

    def get_config(self, instance, vif, image_meta, inst_type):
        conf = super(VRouterVIFDriver, self).get_config(instance, vif,
                image_meta, inst_type)
        dev = self.get_vif_devname(vif)
        designer.set_vif_host_backend_ethernet_config(conf, dev)

        return conf
    #end get_config

    def plug(self, instance, vif):
        iface_id = vif['id']
        dev = self.get_vif_devname(vif)
        linux_net.create_tap_dev(dev)
        LOG.debug(_('Plug %s[%s]' % (instance['display_name'], iface_id)))

        self._vrouter.add_port(
          vm_uuid_str=instance['uuid'],
          vif_uuid_str=iface_id,
          interface_name=dev,
          mac_address=vif['address'],
          ip_address=vif['network']['subnets'][0]['ips'][0]['address'],
          network_uuid=vif['network']['id'],
          display_name=instance['display_name'],
          hostname=instance['host'],
          vm_project_uuid=instance['project_id']
                )
    #end plug

    def unplug(self, instance, vif):
        """Unplug the VIF from the network by deleting the port from
        the bridge."""
        iface_id = vif['id']
        dev = self.get_vif_devname(vif)
        LOG.debug(_('Unplug %s[%s]' % (instance['display_name'], iface_id)))

        self._vrouter.delete_port(iface_id)

        linux_net.delete_net_dev(dev)

    #end unplug
#end class VRouterVIFDriver
