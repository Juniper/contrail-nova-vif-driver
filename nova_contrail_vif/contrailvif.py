import copy
import gettext

gettext.install('contrail_vif')

from oslo.config import cfg

from nova import exception
from nova.network import linux_net
from nova.network import model as network_model
from nova.openstack.common import log as logging
from nova.openstack.common import loopingcall
from nova import utils
from nova.virt.libvirt import config as vconfig
from nova.virt.libvirt import designer
from nova.virt.libvirt.vif import LibvirtBaseVIFDriver
from gen_py.instance_service import InstanceService

LOG = logging.getLogger(__name__)

class VRouterVIFDriver(LibvirtBaseVIFDriver):
    """VIF driver for VRouter when running Quantum."""
    
    def __init__(self, get_connection):
        super(VRouterVIFDriver, self).__init__(get_connection)
        self._agent_alive = False
        self._agent_connected = False
        self._port_dict = {}
        self._protocol = None
        timer = loopingcall.FixedIntervalLoopingCall(self._keep_alive)
        timer.start(interval=2)
    #end __init__

    def _agent_connect(self, protocol):
        # Agent connect for first time
        if protocol != None:
            #from instance_service import InstanceService
	    service = InstanceService.Client(protocol)
	    return service.Connect()
        else:
            return False

    #end __agent_connect

    def _keep_alive(self):
        try:
            if self._agent_alive == False:
                self._protocol = self._agent_conn_open()
                if self._protocol == None:
                    return

            #from instance_service import InstanceService
            service = InstanceService.Client(self._protocol)
            aa_latest = service.KeepAliveCheck()
            if self._agent_alive == False and aa_latest == True:
                port_l = [v for k, v in self._port_dict.iteritems()]
                LOG.debug(_('Agent sending port list %d, %s'), len(port_l), self)
                if len(port_l):
                    for i in range(len(port_l)):
                        LOG.debug(_('Port %s %s'), port_l[i].tap_name, port_l[i].ip_address)

                service.AddPort(port_l)
                self._agent_alive = True
                return

            if self._agent_alive == True and aa_latest == False:
                LOG.debug(_('Agent not available, %s'), self)
                self._agent_alive = False
                return

        except:
            self._agent_alive = False
            LOG.debug(_('Agent keep alive exception: %s'), self)
    #end _keep_alive

    def _agent_conn_open(self):
        import socket
        import sys
        import uuid

        from thrift.transport import TTransport, TSocket
        from thrift.transport.TTransport import TTransportException
        from thrift.protocol import TBinaryProtocol, TProtocol
        #from instance_service import InstanceService
        from gen_py.instance_service import ttypes

        try:
            socket = TSocket.TSocket("127.0.0.1", 9090)
            transport = TTransport.TFramedTransport(socket)
            transport.open()
            protocol = TBinaryProtocol.TBinaryProtocol(transport)
            self._agent_connected = self._agent_connect(protocol)
            return protocol
        except TTransportException:
            return None
    #end _agent_conn_open

    def _convert_to_bl(self, id):
        import uuid
        hexstr = uuid.UUID(id).hex
        return [int(hexstr[i:i+2], 16) for i in range(32) if i%2 == 0]
    #end _convert_to_bl

    def _agent_inform(self, port, id, add):
        # First add to the port list
        if add == True:
            self._port_dict[id] = port
        else:
            if id in self._port_dict:
                del self._port_dict[id]

        if not self._agent_alive:
            return

        #from instance_service import InstanceService
        LOG.debug(_('agent_inform %s, %s, %s, %s'), 
                  port.ip_address, 
                  port.tap_name,
                  add,
                  self)
        import socket
        try:
            service = InstanceService.Client(self._protocol)
            if add == True:
                service.AddPort([port])
            else:
                service.DeletePort(port.port_id)
        except:
            self._agent_alive = False

    #end _agent_inform

    def get_config(self, instance, vif, image_meta, inst_type):
        conf = super(VRouterVIFDriver, self).get_config(instance, vif, image_meta, inst_type)
        dev = self.get_vif_devname(vif)
        designer.set_vif_host_backend_ethernet_config(conf, dev)
    
        return conf

    def plug(self, instance, vif):
        iface_id = vif['id']
        dev = self.get_vif_devname(vif)
        linux_net.create_tap_dev(dev)

        # port_id(tuuid), instance_id(tuuid), tap_name(string), 
        # ip_address(string), vn_id(tuuid)
        import socket
        from gen_py.instance_service import ttypes

        ipv4_address = None
        ipv6_address = None
        subnets = vif['network']['subnets']
        for subnet in subnets:
            ips = subnet['ips'][0]
            if (ips['version'] == 4):
                if ips['address'] is not None: 
                    ipv4_address = ips['address']
            if (ips['version'] == 6):
                if ips['address'] is not None: 
                    ipv6_address = ips['address']

        port = ttypes.Port(self._convert_to_bl(iface_id), 
                           self._convert_to_bl(instance['uuid']), 
                           dev, 
                           ipv4_address,
                           self._convert_to_bl(vif['network']['id']),
                           vif['address'],
	                   instance['display_name'],
	                   instance['hostname'],
	                   instance['host'],
	                   self._convert_to_bl(instance['project_id']),
                           None,
                           None,
                           ipv6_address)

        self._agent_inform(port, iface_id, True)
    #end plug

    def unplug(self, instance, vif):
        """Unplug the VIF from the network by deleting the port from
        the bridge."""
        LOG.debug(_('Unplug'))
        iface_id = vif['id']
        dev = self.get_vif_devname(vif)

        import socket
        from gen_py.instance_service import ttypes

        ipv4_address = None
        ipv6_address = None
        subnets = vif['network']['subnets']
        for subnet in subnets:
            ips = subnet['ips'][0]
            if (ips['version'] == 4):
                if ips['address'] is not None: 
                    ipv4_address = ips['address']
            if (ips['version'] == 6):
                if ips['address'] is not None: 
                    ipv6_address = ips['address']

        port = ttypes.Port(self._convert_to_bl(iface_id), 
                           self._convert_to_bl(instance['uuid']), 
                           dev, 
                           ipv4_address,
                           self._convert_to_bl(vif['network']['id']),
                           vif['address'],
	                   instance['display_name'],
	                   instance['hostname'],
	                   instance['host'],
	                   self._convert_to_bl(instance['project_id']),
                           None,
                           None,
                           ipv6_address)

        self._agent_inform(port, iface_id, False)
        linux_net.delete_net_dev(dev)

    #end unplug
#end class VRouterVIFDriver
