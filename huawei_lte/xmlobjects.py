import xml.etree.ElementTree as ET
import inspect

import huawei_lte.utils as utils
from huawei_lte.errors import RouterError

class XmlObject(object):
    '''A simple object to handle XML object serialisation'''

    def __init__(self, settings=None):
        self._SKIP_BLANK = self._get_param(settings, 'skip_blanks', False)
        self._SKIP_CLASS_ELEMENT = self._get_param(settings, 'skip_class_element', False)

    @classmethod
    def _get_param(cls, vals, key, default=None):
        return utils.get_param(vals, key, default)

    def getPropertyNames(self):
        result = []
        for prop in vars(self).keys():
            if (prop[:1] == '_'):
                continue
            result.append(prop)
        return result

    def getValue(self, prop):
        return getattr(self, prop)

    def getElementName(self):
        return self.__class__.__name__

    def buildXmlRequest(self): return self.buildXML(root='request')
    def buildXmlResponse(self): return self.buildXML(root='response')
    def buildXmlError(self): return self.buildXML(root='error')
    def buildXML(self, header=True, root='request'):
        result = []
        if (header):
            result.append('<?xml version="1.0" encoding="UTF-8"?>')
            result.append('<'+root+'>')
        for prop in self.getPropertyNames():
            value = self.getValue(prop)
            skip_blank = self._SKIP_BLANK and (value is None or value == '')
            if skip_blank or prop[:1] == '_':
                continue
            result.extend(['<', prop, '>'])
            if (type(value) is list):
                for v in value:
                    if (issubclass(type(v), XmlObject)):
                        if not self._SKIP_CLASS_ELEMENT:
                            result.extend(['<', v.getElementName(), '>'])
                        result.append(v.buildXML(False))
                        if not self._SKIP_CLASS_ELEMENT:
                            result.extend(['</', v.getElementName(), '>'])
                    else:
                        result.append(v.buildXML(False))
            elif (issubclass(type(value), XmlObject)):
                result.extend(['<', v.getElementName(), '>'])
                result.append(value.buildXML(False))
                result.extend(['</', v.getElementName(), '>'])
            else:
                result.append(str(value))
            result.extend(['</', prop, '>'])
        if (header):
            result.append('</'+root+'>')
        return ''.join(result)

    def child(self, name, xml):
        return None

    def parseXML(self, xmlText):
        xml = ET.fromstring(xmlText.encode('utf-8'))
        for prop in self.getPropertyNames():
            value = self.getValue(prop)
            if isinstance(value, list):
                parent = xml.find('./'+prop)
                if (parent is not None):
                    for elm in parent.getchildren():
                        xml = ET.tostring(elm, encoding='utf8', method='xml')
                        child = self.child(prop, xml)
                        value.append(child)
            elif (issubclass(type(value), XmlObject)):
                elm = xml.find('./'+prop)
                if (elm is not None):
                    cls = type(value)
                    setattr(self, prop, cls(xml))
            else:
                elm = xml.find('./'+prop)
                if (elm is not None):
                    val = elm.text
                    if (val is None):
                        val = ''
                    setattr(self, prop, val)

class Error(XmlObject):
    PYTHON_API_ERROR_CODE=2000

    def __init__(self, code=0, msg=''):
        super(Error, self).__init__()
        self.code = code
        self.message = msg

    @classmethod
    def xml_error(cls, caller, err):
        code = cls.PYTHON_API_ERROR_CODE
        msg = RouterError.getErrorMessage(code)
        error = Error(code, msg % (caller, err))
        return error.buildXmlError()

    def parseXML(self, xmlText):
        super(Error, self).parseXML(xmlText)
        if (self.message == ''):
            #lookup error message
            self.message = RouterError.getErrorMessage(self.code)
            
class Function(XmlObject):
    def __init__(self, typ, name, url):
        super(Function, self).__init__({'skip_blanks': True})
        self.Name = '%s.%s' % (typ.lower(), name)
        self.Url = 'api/%s' % url
        self.Error = ''

    def getPropertyNames(self):
        return ['Name','Url','Error']

class TestFunctions(XmlObject):
    def __init__(self):
        super(TestFunctions, self).__init__()
        self.DeviceName = ''
        self.ProductFamily = ''
        self.HardwareVersion = ''
        self.SoftwareVersion = ''
        self.WebUIVersion = ''
        self.MacAddress1 = ''
        self.MacAddress2 = ''
        self.Passed = []
        self.Failed = []

    def getPropertyNames(self):
        return ['DeviceName','ProductFamily','HardwareVersion','SoftwareVersion','WebUIVersion','MacAddress1','MacAddress2','Failed','Passed']

    def addFunction(self, obj, name, url, response):
        func = Function(obj.__class__.__name__, name, url)
        if (RouterError.hasError(response)):
            error = Error()
            error.parseXML(response)
            func.Error = error.code + ": " + error.message
            self.Failed.append(func)
        else:
            self.Passed.append(func)

class VirtualServerCollection(XmlObject):
    def __init__(self):
        super(VirtualServerCollection, self).__init__()
        self.Servers = []

    def child(self, name, xml):
        if name == 'Servers':
            return VirtualServer(xml)
        return None

    def add_service(self, config):
        found = False
        newserver = VirtualServer(config)
        for server in self.Servers:
            if server.VirtualServerIPName == newserver.VirtualServerIPName:
                found = True
                break
        if found:
            raise ValueError('Unable to add port forward [%s], it already exists!' % newserver.VirtualServerIPName)
        self.Servers.append(newserver)

    def remove_service(self, name):
        found = False
        for server in self.Servers:
            if server.VirtualServerIPName == name:
                self.Servers.remove(server)
                found = True
                break
        if not found:
            raise ValueError('Unable to delete port forward [%s], it does not exist' % name)

    def add_udp_service(self, config):
        config['protocol'] = 'UDP'
        self.add_service(config)

    def add_tcp_service(self, config):
        config['protocol'] = 'TCP'
        self.add_service(config)

class VirtualServer(XmlObject):
    PROTOCOLS = {'UDP': 17, 'TCP': 6, 'BOTH': 0}
    def __init__(self, config):
        #Define properties first to support XML serialisation
        super(VirtualServer, self).__init__()
        self.VirtualServerIPName = ''
        self.VirtualServerStatus = 1
        self.VirtualServerRemoteIP = ''
        self.VirtualServerWanPort = 0
        self.VirtualServerWanEndPort = 0
        self.VirtualServerLanPort = 0
        self.VirtualServerLanEndPort = 0
        self.VirtualServerIPAddress = ''
        self.VirtualServerProtocol = ''

        if isinstance(config, str):
            self.parseXML(config)
        else:
            name = self._get_param(config, 'name')
            startWanPort = self._get_param(config, 'startwanport')
            endWanPort = self._get_param(config, 'endwanport', startWanPort)
            startLanPort = self._get_param(config, 'startlanport')
            endLanPort = self._get_param(config, 'endlanport', startLanPort)
            localIp = self._get_param(config, 'localip')
            protocol = self._get_param(config, 'protocol', 'BOTH')
            if protocol not in self.PROTOCOLS:
                raise ValueError('Invalid protocol specified for port forwarding (Virtual Server). Must be one of: [%s]' % ', '.join(self.PROTOCOLS.keys))
            protocol = self.PROTOCOLS[protocol]
            if not utils.isIpValid(localIp):
                raise ValueError('Invalid ipaddress specified for port fowarding target server')
            self.VirtualServerIPName = name
            self.VirtualServerWanPort = startWanPort
            self.VirtualServerWanEndPort = endWanPort
            self.VirtualServerLanPort = startLanPort
            self.VirtualServerLanEndPort = endLanPort
            self.VirtualServerIPAddress = localIp
            self.VirtualServerProtocol = protocol

    def getElementName(self):
        return 'Server'

class DataswitchMode(XmlObject):

    def __init__(self):
        '''
        <dataswitch>1</dataswitch>      
        '''
        super(DataswitchMode, self).__init__()
        self.dataswitch = 1 #ON

    def set_dataswitch_on(self):
        self.dataswitch = 1

    def set_dataswitch_off(self):
        self.dataswitch = 0 

class NetworkMode(XmlObject):
    NET_MODES = {
        'AUTO': '00',
        '2G': '01', #GSM/GPRS/EDGE 850/900/1800/1900MHz
        '3G': '02', #DC-HSPA+/HSPA+/UMTS Band 1/2/5/6/8/19
        '4G': '03'} #Band 1/3/4/5/7/8/20/19/26/28/32/38/40/41

    NET_BANDS = {
        #2G Bands
        'GSM1800':          '0x80',
        'GSM900':          '0x300',
        'GSM850':        '0x80000',
        'GSM1900':      '0x200000',
        #3G Bands
        'W2100':        '0x400000',
        'W1900':        '0x800000',
        'W850':        '0x4000000',
        'W900':  '0x2000000000000',
        'W1700': '0x4000000000000',
        #Unexplained values
        'EXTRA': '0x1000000008000000'
    }

    LTE_BANDS = {
        #Hex determined from integer 2 ** (bandnum-1)
        'B1': 'FDD 2100 Mhz',
        'B2': 'FDD 1900 Mhz',
        'B3': 'FDD 1800 Mhz',
        'B4': 'FDD 1700 Mhz',
        'B5': 'FDD 850 Mhz',
        'B6': 'FDD 800 Mhz',
        'B7': 'FDD 2600 Mhz',
        'B8': 'FDD 900 Mhz',
        'B19': 'FDD 850 Mhz',
        'B20': 'FDD 800 Mhz',
        'B26': 'FDD 850 Mhz',
        'B28': 'FDD 700 Mhz',
        'B32': 'FDD 1500 Mhz',
        'B38': 'TDD 2600 Mhz',
        'B40': 'TDD 2300 Mhz',
        'B41': 'TDD 2500 Mhz'}

    @classmethod
    def get_mode(cls, mode):
        '''
        Returns the matching mode key
        '''
        for key, val in cls.NET_MODES.items():
            if val == mode:
                return key
        raise ValueError('No matching firendly mode name found for [%s]' % mode)

    @classmethod
    def lte_to_hex(cls, bands):
        '''
        Returns bands as hex
        '''
        result = 0
        for band in bands:
            result += 2 ** (int(band[1:]) - 1)
        return hex(result)

    @classmethod
    def lte_from_hex(cls, hexnum):
        '''
        Returns list of bands from provided hex
        '''
        result = []
        for band in cls.LTE_BANDS.keys():
            bint = 2 ** (int(band[1:]) - 1)
            if int(hexnum,16) & bint == bint:
                result.append(band)
        return result

    @classmethod
    def band_to_hex(cls, bands):
        '''
        Returns bands as hex
        '''
        result = 0
        for band in bands:
            result += int(cls.NET_BANDS[band], 16)
        return hex(result)

    @classmethod
    def band_from_hex(cls, hexnum):
        '''
        Returns list of bands from provided hex
        '''
        result = []
        for band, val in cls.NET_BANDS.items():
            bint = int(val, 16)
            if int(hexnum, 16) & bint == bint:
                result.append(band)
        return result

    def __init__(self):
        '''
        <NetworkMode>00</NetworkMode>
        <NetworkBand>100200000CE80380</NetworkBand>
        <LTEBand>80080000C5</LTEBand>        
        '''
        super(NetworkMode, self).__init__()
        self.NetworkMode = '00' #Automatic
        self.NetworkBand = ''
        self.LTEBand = ''

    @classmethod
    def __clean_hex(cls, hexnum):
        return hexnum.replace('0x','').replace('L','').upper()

    def set_lte_band(self, bands):
        for band in bands:
            if band not in self.LTE_BANDS.keys():
                raise ValueError('Band [%s] is not a known LTE band. Expected format is B1, B2 etc...' % band)
        hexnum = self.lte_to_hex(bands)
        self.LTEBand = self.__clean_hex(hexnum)

    def set_network_band(self, bands):
        for band in bands:
            if band not in self.NET_BANDS.keys():
                raise ValueError('Band [%s] is not a known 2G/3G band. Expected format is GSM800, W1900, etc...' % band)
        hexnum = self.band_to_hex(bands)
        self.NetworkBand = self.__clean_hex(hexnum)

    def set_network_mode(self, mode):
        if mode not in self.NET_MODES.keys():
            raise ValueError('Mode [%s] is not a known mode. Expected one of: %s' % (mode, self.NET_MODES.keys()))
        self.NetworkMode = self.NET_MODES[mode]

class LanSettings(XmlObject):
    def __init__(self):
        super(LanSettings, self).__init__()
        self.DhcpLanNetmask = '255.255.255.0'
        self.homeurl = 'homerouter.cpe'
        self.DnsStatus = 1
        self.PrimaryDns = '192.168.8.1'
        self.SecondaryDns = '192.168.8.1'
        self.accessipaddress = ''
        self.DhcpStatus = 1
        self.DhcpIPAddress = '192.168.8.1' #LAN IP Address
        self.DhcpStartIPAddress = '192.168.8.100'
        self.DhcpEndIPAddress = '192.168.8.200'
        self.DhcpLeaseTime = 86400
    
    def setDnsManual(self, config):
        primaryDns = self._get_param(config, 'primary')
        secondaryDns = self._get_param(config, 'secondary', '')
        if (not utils.isIpValid(primaryDns)): raise ValueError("Invalid Primary DNS IP Address: %s" % primaryDns)
        if (secondaryDns != '' and not utils.isIpValid(secondaryDns)): raise ValueError("Invalid Secondary DNS IP Address: %s" % secondaryDns)
        self.DnsStatus = 0
        self.PrimaryDns = primaryDns
        self.SecondaryDns = secondaryDns
    
    def setDnsAutomatic(self):
        self.DnsStatus = 1
    
    def setLanAddress(self, config):
        ipaddress = self._get_param(config, 'ipaddress')
        netmask = self._get_param(config, 'netmask', '255.255.255.0')
        url = self._get_param(config, 'url', 'homerouter.cpe')
        if (not utils.isIpValid(ipaddress)): raise ValueError("Invalid LAN IP Address: %s" % ipaddress)
        if (not utils.isIpValid(netmask)): raise ValueError("Invalid LAN Netmask: %s" % netmask)
        self.DhcpIPAddress = ipaddress
        self.DhcpLanNetmask = netmask
        self.homeurl = url

    def setDhcpOn(self, config):
        startAddress = self._get_param(config, 'startaddress')
        endAddress = self._get_param(config, 'endaddress')
        leaseTime = self._get_param(config, 'leasetime', 86400)
        if not utils.isIpValid(startAddress):
            raise ValueError("Invalid DHCP starting IP Address: %s" % startAddress)
        if not utils.isIpValid(endAddress):
            raise ValueError("Invalid DHCP ending IP Address: %s" % endAddress)
        self.DhcpStatus = 1
        self.DhcpStartIPAddress = startAddress
        self.DhcpEndIPAddress = endAddress
        self.DhcpLeaseTime = leaseTime
    def setDhcpOff(self):
        self.DhcpStatus = 0

class MacFilter(XmlObject):
    def __init__(self, value):
        super(MacFilter, self).__init__()
        if not utils.isMacValid(value):
            raise ValueError("Invalid MAC Address to filter: %s" % value)
        self.value=value
        self.status=1
    
    def getElementName(self):
        return self.__class__.__name__.lower()

class MacFilterCollection(XmlObject):
    MODE_DISABLE=0
    MODE_ALLOW=1
    MODE_DENY=2
    def __init__(self):
        super(MacFilterCollection, self).__init__()
        self.policy=self.MODE_DENY
        self.macfilters=[]
    def setAllow(self): self.policy=self.MODE_ALLOW
    def setDeny(self): self.policy=self.MODE_DENY
    def setDisabled(self): self.policy=self.MODE_DISABLE
    def addMac(self, macfilter):
        self.macfilters.append(macfilter)

class StaticHostCollection(XmlObject):
    def __init__(self):
        super(StaticHostCollection, self).__init__()
        self.Hosts = []
    
    def hasHost(self, mac):
        for host in self.Hosts:
            if host.HostHw == mac:
                return True
        return False

    def addHost(self, config):
        host = StaticHost(config)
        if self.hasHost(host.HostHw):
            raise ValueError('The MAC Address to add [%s] is already a static host' % host.HostHw)
        host.HostIndex = len(self.Hosts)+1
        self.Hosts.append(host)

    def removeHost(self, mac):
        found = False
        for host in self.Hosts:
            if host.HostHw == mac:
                self.Hosts.remove(host)
                found = True
                break
        if not found:
            raise ValueError('The MAC Address to remove [%s] is not a current static host' % mac)
        #Reindex
        for i in range(len(self.Hosts)):
            self.Hosts[i].HostIndex = i+1

    def getElementName(self):
        return 'Hosts'

    def child(self, name, xml):
        if name == self.getElementName():
            return StaticHost(xml)
        else:
            return None

class StaticHost(XmlObject):
    '''
    Represents an static IP Address for a specific MAC address
    '''
    P_MAC_ADDRESS = 'macaddress'
    P_IP_ADDRESS = 'ipaddress'

    def __init__(self, config):
        super(StaticHost, self).__init__()
        self.HostIndex = 0
        self.HostHw = ''
        self.HostIp = ''
        self.HostEnabled = 1
        if isinstance(config, str):
            self.parseXML(config)
        else:
            mac = self._get_param(config, self.P_MAC_ADDRESS)
            ip = self._get_param(config, self.P_IP_ADDRESS)
            if (not utils.isMacValid(mac)): raise ValueError("Invalid static host MAC address: %s" % mac)
            if (not utils.isIpValid(ip)): raise ValueError("Invalid static host IP Address: %s" % ip)
            self.HostHw = mac
            self.HostIp = ip
    
    def getElementName(self):
        return 'Host'

class CustomXml(XmlObject):
    def __init__(self, props, element_name=None):
        super(CustomXml, self).__init__({'skip_class_element': True})
        if element_name is None:
            element_name = self.__class__.__name__
        self.ele_name = element_name
        self.vals = props.copy()
    def getPropertyNames(self):
        return self.vals.keys()
    def getValue(self, property):
        return self.vals[property]
    def getElementName(self): return self.ele_name

class RouterControl(XmlObject):
    NONE = -1
    REBOOT = 1
    POWEROFF = 4
    def __init__(self, control):
        super(RouterControl, self).__init__()
        self.Control = control
    
    @classmethod
    def reboot(cls): return RouterControl(cls.REBOOT)

    @classmethod
    def poweroff(cls): return RouterControl(cls.POWEROFF)

class SipOptions(XmlObject):
    P_CALL_WAITING = 'callwaiting'

    def __init__(self, config):
        super(SipOptions, self).__init__()
        self.callwaitingenable = self._get_param(config, P_CALL_WAITING, 0)
    
    def enableCallWaiting(self):
        self.callwaitingenable=1

    def disableCallWaiting(self):
        self.callwaitingenable=0

class SipServer(XmlObject):
    P_PROXY_ADDRESS = 'proxy_address'
    P_PROXY_PORT = 'proxy_port'
    P_REGISTER_ADDRESS = 'register_address'
    P_REGISTER_PORT = 'register_port'
    P_SIP_DOMAIN = 'sip_domain'
    P_SECONDARY_SERVER = 'is_secondary'

    def __init__(self, config):
        super(SipServer, self).__init__()

        #Primary
        self.proxyserveraddress = self._get_param(config, self.P_PROXY_ADDRESS)
        self.proxyserverport = self._get_param(config, self.P_PROXY_PORT)
        self.registerserveraddress = self._get_param(config, self.P_REGISTER_ADDRESS)
        self.registerserverport = self._get_param(config, self.P_REGISTER_PORT)
        self.sipserverdomain = self._get_param(config, self.P_SIP_DOMAIN)

        #Secondary
        self.secondproxyserveraddress = ''
        self.secondproxyserverport = ''
        self.secondregisterserveraddress = ''
        self.secondregisterserverport = ''
        self.secondsipserverdomain = ''

    def add_secondary(self, config):
        self.secondproxyserveraddress = self._get_param(config, self.P_PROXY_ADDRESS)
        self.secondproxyserverport = self._get_param(config, self.P_PROXY_PORT)
        self.secondregisterserveraddress = self._get_param(config, self.P_REGISTER_ADDRESS)
        self.secondregisterserverport = self._get_param(config, self.P_REGISTER_PORT)
        self.secondsipserverdomain = self._get_param(config, self.P_SIP_DOMAIN)

class SipAccount(XmlObject):
    P_ACCOUNT = 'account'
    P_USERNAME = 'username'
    P_PASSWORD = 'password'
    #registerstatus:registerStatus,
    #index: editIndex

    def __init__(self, config):
        super(SipAccount, self).__init__()
        self.username = self._get_param(config, self.P_USERNAME)
        self.password = self._get_param(config, self.P_PASSWORD)
        self.account = self._get_param(config, self.P_ACCOUNT)
        self.registerstatus = ''
        self.index = 0

    def getElementName(self):
        return 'account'

class SipCollection(XmlObject):
    '''
    '''
    def __init__(self):
        super(SipCollection, self).__init__()
        self.account = []

    def addAccount(self, config):
        rec = SipAccount(config)
        rec.index = len(self.account)
        self.account.append(rec)
        return rec

class VoiceSettings(XmlObject):
    '''
    {'cid_type': 'FSK|DTMF', 'dtmf_method': 'INBOUND|OUTBAND'}
    '''
    DTMF_INBAND = 0
    DTMF_OUTBAND = 1
    CID_FSK = 1
    CID_DTMF = 2

    P_CID_SEND_TYPE = 'cid_send_type'
    P_CS_DTMF_METHOD = 'cs_dtmf_method'

    def __init__(self, config):
        super(VoiceSettings, self).__init__()
        self.cid_send_type = self.CID_DTMF if self._get_param(config, self.P_CID_SEND_TYPE).upper() == 'DTMF' else self.CID_FSK
        self.cs_dtmf_method = self.DTMF_OUTBAND if self._get_param(config, self.P_CS_DTMF_METHOD).upper() == 'OUTBAND' else self.DTMF_INBAND

class Ddns(XmlObject):
    P_USERNAME = 'username'
    P_PASSWORD = 'password'
    P_PROVIDER = 'provider'
    P_DOMAIN = 'domain'

    PROVIDERS = ["DynDNS.org", "No-IP.com", "oray"]
    def __init__(self, config):
        super(Ddns, self).__init__()
        provider = self._get_param(config, self.P_PROVIDER)
        if (not provider in self.PROVIDERS):
            raise ValueError('Invalid DDNS service provided, it must be one of: [%s]' % ', '.join(self.PROVIDERS))
        self.provider = provider
        self.username = self._get_param(config, self.P_USERNAME)
        self.password = self._get_param(config, self.P_PASSWORD)
        self.domainname = self._get_param(config, self.P_DOMAIN)
        self.status = 1
        self.index = 0

    def getElementName(self):
        return self.__class__.__name__.lower()

class DdnsCollection(XmlObject):
    '''
    Provides support for dynamic DNS providers: NoIp, DynDns, Oray
    '''
    OPERATE_ADD = 1
    OPERATE_DELETE = 2
    OPERATE_EDIT = 3

    def __init__(self):
        super(DdnsCollection, self).__init__()
        self.ddnss = []
        self.operate = self.OPERATE_ADD
    
    def addNoIpDdns(self, config):
        config[Ddns.P_PROVIDER] = Ddns.PROVIDERS[1]
        return self.addDdns(config)

    def addDynDnsDdns(self, config):
        config[Ddns.P_PROVIDER] = Ddns.PROVIDERS[0]
        return self.addDdns(config)

    def addOrayDdns(self, config):
        config[Ddns.P_PROVIDER] = Ddns.PROVIDERS[2]
        return self.addDdns(config)

    def addDdns(self, config):
        rec = Ddns(config)
        rec.index = len(self.ddnss)
        self.ddnss.append(rec)
        return rec

    def setToAdd(self):
        self.operate = self.OPERATE_ADD

    def setToDelete(self):
        self.operate = self.OPERATE_DELETE

    def setToEdit(self):
        self.operate = self.OPERATE_EDIT

class ConnectionMode(XmlObject):
    '''
    Represents an ethernet configuration
    '''

    P_PRIMARY_DNS = 'primarydns'
    P_SECONDARY_DNS = 'secondarydns'
    P_DNS_MANUAL = 'dnsmanual'
    P_MTU = 'mtu'

    P_PPOE_PASSWORD = 'password'
    P_PPOE_USERNAME = 'username'
    P_PPOE_AUTH = 'authmode'
    
    P_DIAL_MODE = 'dialmode'
    P_MAX_IDLE = 'maxidletime'

    P_STATIC_IP_ADDRESS = 'ipaddress'
    P_STATIC_NETMASK = 'netmask'
    P_STATIC_GATEWAY = 'gateway'
    P_STATIC_PRIMARY_DNS = 'primarydns'
    P_STATIC_SECONDARY_DNS = 'secondarydns'


    MODE_AUTO = 0
    MODE_PPPOE_DYNAMIC = 1
    MODE_PPPOE = 2
    MODE_DYNAMIC = 3
    MODE_STATIC = 4
    MODE_LAN = 5

    #Best guess, PPOE authentication
    AUTH_AUTO = 0
    AUTH_PAP = 1
    AUTH_CHAP = 2

    #Dialup mode
    DIAL_AUTO = 0
    DIAL_ON_DEMAND = 1

    NO_DNS = '0.0.0.0'

    def __init__(self):
        super(ConnectionMode, self).__init__()
        self.connectionmode = self.MODE_AUTO
        self.pppoemtu = 1480
        self.dynamicipmtu = 1500
        self.maxidletime = 600
        self.dynamicsetdnsmanual = 0
        self.dynamicprimarydns = self.NO_DNS
        self.dynamicsecondarydns = self.NO_DNS
        self.primarydns = self.NO_DNS
        self.secondarydns = self.NO_DNS
        self.netmask = ''
        self.ipaddress = ''
        self.gateway = ''
        self.pppoeuser = ''
        self.pppoepwd = ''
        self.pppoeauth = self.AUTH_PAP

    def set(self, mode, config=False):
        self.connectionmode = mode
        if not config:
            if mode == self.MODE_AUTO or mode == self.MODE_LAN: return
            else: config = {}

        #Set values only if they exist in the supplied config

        if mode == self.MODE_DYNAMIC or mode == self.MODE_PPPOE_DYNAMIC or mode == self.MODE_AUTO:
            if self.P_PRIMARY_DNS in config:
                dns = self._get_param(config, self.P_PRIMARY_DNS)
                if dns == '': dns = self.NO_DNS
                if (dns != self.NO_DNS):
                    if (not utils.isIpValid(dns)): raise ValueError("Invalid IP Address for Dynamic Primary DNS: %s" % dns)
                self.dynamicprimarydns = dns
                if dns != self.NO_DNS:
                    self.dynamicsetdnsmanual = 1
                else:
                    self.dynamicsetdnsmanual = 0

            if self.P_SECONDARY_DNS in config:
                dns = self._get_param(config, self.P_SECONDARY_DNS)
                if dns == '': dns = self.NO_DNS
                if (dns != self.NO_DNS):
                    if (not utils.isIpValid(dns)): raise ValueError("Invalid IP Address for Dynamic Secondary DNS: %s" % dns)
                self.dynamicsecondarydns = dns
                if dns != self.NO_DNS: self.dynamicsetdnsmanual = 1

            if self.P_DNS_MANUAL in config:
                dns = self._get_param(config, self.P_DNS_MANUAL)
                if dns not in [0,1]: raise ValueError("%s must be 1 or 0: %s" % (self.P_DNS_MANUAL, dns))
                if self.dynamicprimarydns == self.NO_DNS: raise ValueError("Manual DNS specified, Primary DNS must be set")
                self.dynamicsetdnsmanual = dns

            if self.P_MTU in config:
                self.dynamicipmtu = self._get_param(config, self.P_MTU)

        if mode == self.MODE_PPPOE or mode == self.MODE_PPPOE_DYNAMIC or mode == self.MODE_AUTO:
            if self.P_PPOE_PASSWORD in config:
                val = self._get_param(config, self.P_PPOE_PASSWORD)
                if len(val) > 63: raise ValueError('PPPOE password can contain a maximum of 63 characters, including letters, numbers, and symbols (ASCII characters 32-126).')
                self.pppoepwd = val
            elif mode != self.MODE_AUTO and self.pppoepwd == '':
                raise ValueError('PPOE password must be provided')

            if self.P_PPOE_USERNAME in config:
                val = self._get_param(config, self.P_PPOE_USERNAME)
                if len(val) > 63: raise ValueError('PPPOE user can contain a maximum of 63 characters, including letters, numbers, and symbols (ASCII characters 32-126).')
                self.pppoeuser = val
            elif mode != self.MODE_AUTO and self.username == '':
                raise ValueError('PPOE username must be provided')

            if self.P_PPOE_AUTH in config:
                mode = self._get_param(config, self.P_PPOE_AUTH)
                if not mode in [self.AUTH_AUTO, self.AUTH_PAP, self.AUTH_CHAP]: raise ValueError('PPOE auth mode must be one of: 0 (AUTO), 1 (PAP), 2 (CHAP)')
                self.pppoeauth = self._get_param(config, self.P_PPOE_AUTH)

            if self.P_MTU in config:
                self.pppoemtu = self._get_param(config, self.P_MTU)

        if mode == self.MODE_STATIC:

            if self.P_STATIC_IP_ADDRESS in config:
                ip = self._get_param(config, self.P_STATIC_IP_ADDRESS)
                if (not utils.isIpValid(ip)): raise ValueError("Invalid IP Address: %s" % ip)
                self.ipaddress = ip
                self.netmask = '255.255.255.0'
            else:
                raise ValueError('%s must be provided' % self.P_STATIC_IP_ADDRESS)

            if self.P_STATIC_NETMASK in config:
                self.netmask = self._get_param(config, self.P_STATIC_NETMASK)

            if self.P_STATIC_GATEWAY in config:
                self.gateway = self._get_param(config, self.P_STATIC_GATEWAY)
            else:
                if self.gateway == '':
                    raise ValueError('%s must be provided' % self.P_STATIC_GATEWAY)

            if self.P_MTU in config:
                self.staticipmtu = self._get_param(config, self.P_MTU)

            if self.P_STATIC_PRIMARY_DNS in config:
                dns = self._get_param(config, self.P_STATIC_PRIMARY_DNS)
                if (not utils.isIpValid(dns)): raise ValueError("Invalid IP Address for Primary DNS: %s" % dns)
                self.primarydns = dns

            if self.P_STATIC_SECONDARY_DNS in config:
                dns = self._get_param(config, self.P_STATIC_SECONDARY_DNS)
                if (not utils.isIpValid(dns)): raise ValueError("Invalid IP Address for Secondary DNS: %s" % dns)
                self.secondarydns = dns

        if self.P_MAX_IDLE in config:
            self.maxidletime = self._get_param(config, self.P_MAX_IDLE)

        if self.P_DIAL_MODE in config:
            mode = self._get_param(config, self.P_DIAL_MODE)
            if not mode in [self.DIAL_AUTO, self.DIAL_ON_DEMAND]: raise ValueError('PPOE dial up mode must be one of: 0 (AUTO), 1 (On Demand)')
            self.dialmode = mode

        #PPPOE
