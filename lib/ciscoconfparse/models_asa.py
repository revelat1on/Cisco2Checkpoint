import re

from protocol_values import ASA_TCP_PORTS, ASA_UDP_PORTS, ASA_IP_PROTOCOLS
from ccp_abc import BaseCfgLine
from ccp_util import L4Object
from ccp_util import IPv4Obj

### HUGE UGLY WARNING:
###   Anything in models_asa.py could change at any time, until I remove this
###   warning.  I have good reason to believe that these methods 
###   function correctly, but I've been wrong before.  There are no unit tests
###   for this functionality yet, so I consider all this code alpha quality. 
###
###   Use models_asa.py at your own risk.  You have been warned :-)

""" models_asa.py - Parse, Query, Build, and Modify IOS-style configurations
     Copyright (C) 2014-2015 David Michael Pennington

     This program is free software: you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation, either version 3 of the License, or
     (at your option) any later version.

     This program is distributed in the hope that it will be useful,
     but WITHOUT ANY WARRANTY; without even the implied warranty of
     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
     GNU General Public License for more details.

     You should have received a copy of the GNU General Public License
     along with this program.  If not, see <http://www.gnu.org/licenses/>.

     If you need to contact the author, you can do so by emailing:
     mike [~at~] pennington [/dot\] net
"""

##
##-------------  ASA supported protocols, operators and port names
##

_IP_PROTO = 'tcp|udp|tcp-udp'
_ALL_PROTOCOLS = 'ip|tcp|udp|icmp|ahp|ah|eigrp|esp|gre|igmp|igrp|ipinip|ipsec'\
                '|ospf|pcp|pim|pptp|snp|\d+'
_PORT_SIMPLE_OP = 'eq|neq|lt|gt'
_PORT_NAMES = r'aol|bgp|chargen|cifs|citrix-ica|cmd|ctiqbe|daytime'\
                '|discard|domain|echo|exec|finger|tftp|ftp|ftp-data|gopher'\
                '|h323|hostname|http|https|ident|imap4|irc|kerberos|klogin'\
                '|kshell|ldap|ldaps|login|lotusnotes|lpd|netbios-ssn|nfs'\
                '|nntp|ntp|pcanywhere-data|pim-auto-rp|pop2|pop3|pptp|rsh'\
                '|rtsp|sip|smtp|sqlnet|ssh|sunrpc|tacacs|talk|telnet|uucp'\
                '|whois|www|netbios-ns|netbios-dgm|netbios-ss|snmptrap|snmp'\
                '|syslog|isakmp|bootps|bootpc|radius|\d+'
_ACL_ICMP_PROTOCOLS = 'alternate-address|conversion-error|echo-reply|echo'\
                '|information-reply|information-request|mask-reply'\
                '|mask-request|mobile-redirect|parameter-problem|redirect'\
                '|router-advertisement|router-solicitation|source-quench'\
                '|time-exceeded|timestamp-reply|timestamp-request|traceroute'\
                '|unreachable'
##
##-------------  ASA Configuration line object
##

class ASACfgLine(BaseCfgLine):
    """An object for a parsed ASA-style configuration line.  
    :class:`~models_asa.ASACfgLine` objects contain references to other 
    parent and child :class:`~models_asa.ASACfgLine` objects.

    .. note::

       Originally, :class:`~models_asa.ASACfgLine` objects were only 
       intended for advanced ciscoconfparse users.  As of ciscoconfparse 
       version 0.9.10, *all users* are strongly encouraged to prefer the 
       methods directly on :class:`~models_asa.ASACfgLine` objects.  
       Ultimately, if you write scripts which call methods on 
       :class:`~models_asa.ASACfgLine` objects, your scripts will be much 
       more efficient than if you stick strictly to the classic 
       :class:`~ciscoconfparse.CiscoConfParse` methods.

    Args:
        - text (str): A string containing a text copy of the ASA configuration line.  :class:`~ciscoconfparse.CiscoConfParse` will automatically identify the parent and children (if any) when it parses the configuration. 
        - comment_delimiter (str): A string which is considered a comment for the configuration format.  Since this is for Cisco ASA-style configurations, it defaults to ``!``.

    Attributes:
        - text     (str): A string containing the parsed ASA configuration statement
        - linenum  (int): The line number of this configuration statement in the original config; default is -1 when first initialized.
        - parent (:class:`~models_asa.ASACfgLine()`): The parent of this object; defaults to ``self``.
        - children (list): A list of ``ASACfgLine()`` objects which are children of this object.
        - child_indent (int): An integer with the indentation of this object's children
        - indent (int): An integer with the indentation of this object's ``text``
        - oldest_ancestor (bool): A boolean indicating whether this is the oldest ancestor in a family
        - is_comment (bool): A boolean indicating whether this is a comment

    Returns:
        - an instance of :class:`~models_asa.ASACfgLine`.

    """
    def __init__(self, *args, **kwargs):
        """Accept an ASA line number and initialize family relationship
        attributes"""
        super(ASACfgLine, self).__init__(*args, **kwargs)

    @classmethod
    def is_object_for(cls, line="", re=re):
        ## Default object, for now
        return True

    @property
    def is_intf(self):
        # Includes subinterfaces
        intf_regex = r'^interface\s+(\S+.+)'
        if self.re_match(intf_regex):
            return True
        return False

    @property
    def is_subintf(self):
        intf_regex = r'^interface\s+(\S+?\.\d+)'
        if self.re_match(intf_regex):
            return True
        return False

    @property
    def is_virtual_intf(self):
        intf_regex = r'^interface\s+(Loopback|Tunnel|Virtual-Template|Port-Channel)'
        if self.re_match(intf_regex):
            return True
        return False

    @property
    def is_loopback_intf(self):
        intf_regex = r'^interface\s+(\Soopback)'
        if self.re_match(intf_regex):
            return True
        return False

    @property
    def is_ethernet_intf(self):
        intf_regex = r'^interface\s+(.*?\Sthernet)'
        if self.re_match(intf_regex):
            return True
        return False

##
##-------------  ASA Interface ABC
##

# Valid method name substitutions:
#    switchport -> switch
#    spanningtree -> stp
#    interfce -> intf
#    address -> addr
#    default -> def

class BaseASAIntfLine(ASACfgLine):
    def __init__(self, *args, **kwargs):
        super(BaseASAIntfLine, self).__init__(*args, **kwargs)
        self.ifindex = None    # Optional, for user use
        self.default_ipv4_addr_object = IPv4Obj('127.0.0.1/32', 
            strict=False)

    def __repr__(self):
        if not self.is_switchport:
            if self.ipv4_addr_object==self.default_ipv4_addr_object:
                addr = "No IPv4"
            else:
                addr = self.ipv4_addr_object
            return "<%s # %s '%s' info: '%s'>" % (self.classname, 
                self.linenum, self.name, addr)
        else:
            return "<%s # %s '%s' info: 'switchport'>" % (self.classname, self.linenum, self.name)

    def reset(self, atomic=True):
        # Insert build_reset_string() before this line...
        self.insert_before(self.build_reset_string(), atomic=atomic)

    def build_reset_string(self):
        # ASA interfaces are defaulted like this...
        raise NotImplementedError

    @property
    def verbose(self):
        if not self.is_switchport:
            return "<%s # %s '%s' info: '%s' (child_indent: %s / len(children): %s / family_endpoint: %s)>" % (self.classname, self.linenum, self.text, self.ipv4_addr_object or "No IPv4", self.child_indent, len(self.children), self.family_endpoint) 
        else:
            return "<%s # %s '%s' info: 'switchport' (child_indent: %s / len(children): %s / family_endpoint: %s)>" % (self.classname, self.linenum, self.text, self.child_indent, len(self.children), self.family_endpoint) 

    @classmethod
    def is_object_for(cls, line="", re=re):
        return False

    ##-------------  Basic interface properties

    @property
    def name(self):
        """Return a string, such as 'GigabitEthernet0/1'"""
        if not self.is_intf:
            return ''
        intf_regex = r'^interface\s+(\S+[0-9\/\.\s]+)\s*'
        name = self.re_match(intf_regex).strip()
        return name

    @property
    def port(self):
        """Return the interface's port number"""
        return self.ordinal_list[-1]

    @property
    def port_type(self):
        """Return Loopback, GigabitEthernet, etc..."""
        port_type_regex = r'^interface\s+([A-Za-z\-]+)'
        return self.re_match(port_type_regex, group=1, default='')

    @property
    def ordinal_list(self):
        """Return a list of numbers representing card, slot, port for this interface.  If you call ordinal_list on GigabitEthernet2/25.100, you'll get this python list of integers: [2, 25].  If you call ordinal_list on GigabitEthernet2/0/25.100 you'll get this python list of integers: [2, 0, 25].  This method strips all subinterface information in the returned value.

        ..warning:: ordinal_list should silently fail (returning an empty python list) if the interface doesn't parse correctly"""
        if not self.is_intf:
            return []
        else:
            intf_regex = r'^interface\s+[A-Za-z\-]+\s*(\d+.*?)(\.\d+)*(\s\S+)*\s*$'
            intf_number = self.re_match(intf_regex, group=1, default='')
            if intf_number:
                return [int(ii) for ii in intf_number.split('/')]
            else:
                return []

    @property
    def description(self):
        retval = self.re_match_iter_typed(r'^\s*description\s+(\S.+)$',
            result_type=str, default='')
        return retval


    @property
    def manual_delay(self):
        retval = self.re_match_iter_typed(r'^\s*delay\s+(\d+)$',
            result_type=int, default=0)
        return retval


    @property
    def ipv4_addr_object(self):
        """Return a ccp_util.IPv4Obj object representing the address on this interface; if there is no address, return IPv4Obj('127.0.0.1/32')"""
        try:
            return IPv4Obj('%s/%s' % (self.ipv4_addr, self.ipv4_netmask))
        except:
            return self.default_ipv4_addr_object

    @property
    def ipv4_standby_addr_object(self):
        """Return a ccp_util.IPv4Obj object representing the standby address on this interface; if there is no address, return IPv4Obj('127.0.0.1/32')"""
        try:
            return IPv4Obj('%s/%s' % (self.ipv4_standby_addr, 
                self.ipv4_netmask))
        except:
            return self.default_ipv4_addr_object

    @property
    def ipv4_network_object(self):
        """Return an ccp_util.IPv4Obj object representing the subnet on this interface; if there is no address, return ccp_util.IPv4Obj('127.0.0.1/32')"""
        return self.ip_network_object

    @property
    def ip_network_object(self):
        try:
            return IPv4Obj('%s/%s' % (self.ipv4_addr, self.ipv4_netmask), 
                strict=False).network
        except AttributeError:
            return IPv4Obj('%s/%s' % (self.ipv4_addr, self.ipv4_netmask), 
                strict=False).network_address
        except:
            return self.default_ipv4_addr_object

    @property
    def has_autonegotiation(self):
        if not self.is_ethernet_intf:
            return False
        elif self.is_ethernet_intf and (self.has_manual_speed or self.has_manual_duplex):
            return False
        elif self.is_ethernet_intf:
            return True
        else:
            raise ValueError

    @property
    def has_manual_speed(self):
        retval = self.re_match_iter_typed(r'^\s*speed\s+(\d+)$',
            result_type=bool, default=False)
        return retval


    @property
    def has_manual_duplex(self):
        retval = self.re_match_iter_typed(r'^\s*duplex\s+(\S.+)$',
            result_type=bool, default=False)
        return retval

    @property
    def is_shutdown(self):
        retval = self.re_match_iter_typed(r'^\s*(shut\S*)\s*$',
            result_type=bool, default=False)
        return retval

    @property
    def ip_addr(self):
        return self.ipv4_addr

    @property
    def ipv4_addr(self):
        """Return a string with the interface's IPv4 address, or '' if there is none"""
        retval = self.re_match_iter_typed(r'^\s+ip\s+address\s+(\d+\.\d+\.\d+\.\d+)\s+\d+\.\d+\.\d+\.\d+(\sstandby\s+\S+\s*)*$', 
            result_type=str, default='')
        return retval

    @property
    def ipv4_standby_addr(self):
        """Return a string with the interface's IPv4 address, or '' if there is none"""
        retval = self.re_match_iter_typed(r'^\s+ip\s+address\s+\d+\.\d+\.\d+\.\d+\s+\d+\.\d+\.\d+\.\d+\sstandby\s+(\S+)\s*$', 
            result_type=str, default='')
        return retval

    @property
    def ipv4_netmask(self):
        """Return a string with the interface's IPv4 netmask, or '' if there is none"""
        retval = self.re_match_iter_typed(r'^\s+ip\s+address\s+\d+\.\d+\.\d+\.\d+\s+(\d+\.\d+\.\d+\.\d+)(\sstandby\s+\S+\s*)*$',
            result_type=str, default='')
        return retval

    @property
    def ipv4_masklength(self):
        """Return an integer with the interface's IPv4 mask length, or 0 if there is no IP address on the interace"""
        ipv4_addr_object = self.ipv4_addr_object
        if ipv4_addr_object!=self.default_ipv4_addr_object:
            return ipv4_addr_object.prefixlen
        return 0

    def in_ipv4_subnet(self, ipv4network=IPv4Obj('0.0.0.0/32', strict=False)):
        """Accept two string arguments for network and netmask, and return a boolean for whether this interface is within the requested subnet.  Return None if there is no address on the interface"""
        if not (str(self.ipv4_addr_object.ip)=="127.0.0.1"):
            try:
                # Return a boolean for whether the interface is in that network and mask
                return self.ipv4_addr_object in ipv4network
            except:
                raise ValueError("FATAL: %s.in_ipv4_subnet(ipv4network={0}) is an invalid arg".format(ipv4network))
        else:
            return None

    def in_ipv4_subnets(self, subnets=None):
        """Accept a set or list of ccp_util.IPv4Obj objects, and return a boolean for whether this interface is within the requested subnets."""
        if (subnets is None):
            raise ValueError("A python list or set of ccp_util.IPv4Obj objects must be supplied")
        for subnet in subnets:
            tmp = self.in_ipv4_subnet(ipv4network=subnet)
            if (self.ipv4_addr_object in subnet):
                return tmp
        return tmp

    @property
    def has_ip_pim_sparse_mode(self):
        ## NOTE: I have no intention of checking self.is_shutdown here
        ##     People should be able to check the sanity of interfaces
        ##     before they put them into production

        ## Interface must have an IP addr to run PIM
        if (self.ipv4_addr==''):
            return False

        retval = self.re_match_iter_typed(r'^\s*ip\spim\ssparse-mode\s*$)\s*$',
            result_type=bool, default=False)
        return retval

    @property
    def is_switchport(self):
        retval = self.re_match_iter_typed(r'^\s*(switchport)\s*',
            result_type=bool, default=False)
        return retval

    @property
    def has_manual_switch_access(self):
        retval = self.re_match_iter_typed(r'^\s*(switchport\smode\s+access)\s*$',
            result_type=bool, default=False)
        return retval

    @property
    def has_manual_switch_trunk_encap(self):
        return bool(self.manual_switch_trunk_encap)

    @property
    def has_manual_switch_trunk(self):
        retval = self.re_match_iter_typed(r'^\s*(switchport\s+mode\s+trunk)\s*$',
            result_type=bool, default=False)
        return retval

    @property
    def access_vlan(self):
        """Return an integer with the access vlan number.  Return 0, if the port has no explicit vlan configured."""
        retval = self.re_match_iter_typed(r'^\s*switchport\s+access\s+vlan\s+(\d+)$',
            result_type=int, default=0)
        return retval

##
##-------------  ASA name
##

_RE_NAMEOBJECT_STR = r'^name\s+(?P<addr>\d+\.\d+\.\d+\.\d+)\s(?P<name>\S+)'
_RE_NAMEOBJECT = re.compile(_RE_NAMEOBJECT_STR, re.VERBOSE)
class ASAName(ASACfgLine):

    def __init__(self, *args, **kwargs):
        """Accept an ASA line number and initialize family relationship
        attributes"""
        super(ASAName, self).__init__(*args, **kwargs)
        mm = _RE_NAMEOBJECT.search(self.text)
        if not (mm is None):
            self._mm_results = mm.groupdict()   # All regex match results
        else:
            raise ValueError

        self.name = self._mm_results['name']
        self.addr = self._mm_results['addr']

    @classmethod
    def is_object_for(cls, line="", re=re):
        if 'name ' in line[0:5].lower():
            return True
        return False

    @property
    def result_dict(self):
        mm_r = self._mm_results
        retval = dict()

        retval['name'] = self._mm_results['name']
        retval['addr'] = self._mm_results['addr']

        return retval

##
##-------------  ASA object network
##

_RE_NETOBJ_CHILD_STR = r"""(?:
(^\s+description(?P<description0>.+)$)
|(^\s+host\s+(?P<host1>\S+)$)
|(^\s+subnet\s+(?P<subnet2>\d+\.\d+\.\d+\.\d+)\s+(?P<mask2>\d+\.\d+\.\d+\.\d+)$)
|(^\s+range\s+(?P<range_low3>\d+\.\d+\.\d+\.\d+)\s+(?P<range_high3>\d+\.\d+\.\d+\.\d+)$)
)
"""
_RE_NETOBJ_CHILD = re.compile(_RE_NETOBJ_CHILD_STR, re.VERBOSE)
class ASAObjNetwork(ASACfgLine):

    def __init__(self, *args, **kwargs):
        """Accept an ASA line number and initialize family relationship
        attributes"""
        super(ASAObjNetwork, self).__init__(*args, **kwargs)

    @classmethod
    def is_object_for(cls, line="", re=re):
        if 'object network ' in line[0:15].lower():
            return True
        return False

    @property
    def name(self):
        retval = self.re_match_typed(r'^\s*object\snetwork\s+(\S.+)$',
            result_type=str, default='')
        return retval

    @property
    def description(self):
        regex = r"(^\s+description(?P<description0>.+)$)"
        retval = self.re_match_iter_typed(regex,
            result_type=str, default='')
        return retval

    @property
    def result_dict(self):
        retval = dict()

        for obj in self.children:
            ## Parse out 'service' and 'description' lines
            mm = _RE_NETOBJ_CHILD.search(obj.text)
            if not (mm is None):
                mm_r = mm.groupdict()
            else:
                mm_r = dict()
            
            # host...
            if mm_r.get('host1',None):
                retval['net_method'] = 'host'
                retval['ipaddr'] = mm_r['host1']
                retval['mask'] = '255.255.255.255'
            elif mm_r.get('subnet2',None):
                retval['net_method'] = 'subnet'
                retval['ipaddr'] = mm_r['subnet2']
                retval['mask'] = mm_r['mask2']
            elif mm_r.get('range_low3',None):
                retval['net_method'] = 'range'
                retval['ipaddr_low'] = mm_r['range_low3']
                retval['ipaddr_high'] = mm_r['range_high3']
            # description
            elif mm_r.get('description0',None):
                retval['description'] =  mm_r['description0']
            else:
                raise NotImplementedError("Cannot parse '{0}'".format(obj.text))
        return retval

##
##-------------  ASA object service
##
_RE_SVCOBJ_CHILD_STR = r"""(?: # Non-capturing parentesis
# example:
# service tcp source range 1 65535 destination range 49152 65535
# service tcp source eq bgp destination eq 53
(^\s+description(?P<description0>.+))
|(^\s+service
  \s+(?P<protocol1>{0})
  (?:\s+source
    (?:                         # source port
      (?:\s+
        (?P<src_port_op1>{1})
        \s+(?P<src_port1>(?:(?:{2})\s?)+)
      )
      |(?:\s+range\s+(?P<src_port_low1>\d+)\s+(?P<src_port_high1>\d+))
      |(?:\s+object-group\s+(?P<src_service_group1>\S+))
    )
  )?
  (?:\s+destination
    (?:                         # destination port
      (?:\s+
        (?P<dst_port_op1>{1})
        \s+(?P<dst_port1>(?:(?:{2})\s?)+)
      )
      |(?:\s+range\s+(?P<dst_port_low1>\d+)\s+(?P<dst_port_high1>\d+))
      |(?:\s+object-group\s+(?P<dst_service_group1>\S+))
    )
  )
 )
)                               # Close non-capture parentesis
""".format(_IP_PROTO,_PORT_SIMPLE_OP,_PORT_NAMES)
_RE_SVCOBJ_CHILD = re.compile(_RE_SVCOBJ_CHILD_STR, re.VERBOSE)
class ASAObjService(ASACfgLine):

    def __init__(self, *args, **kwargs):
        """Accept an ASA line number and initialize family relationship
        attributes"""
        super(ASAObjService, self).__init__(*args, **kwargs)

    @classmethod
    def is_object_for(cls, line="", re=re):
        if re.search(r'^(object\sservice)', line):
            return True
        return False

    @property
    def name(self):
        retval = self.re_match_typed(r'^\s*object\sservice\s+(\S.+)$',
            result_type=str, default='')
        return retval

    @property
    def description(self):
        regex = r"(^\s+description(?P<description0>.+)$)"
        retval = self.re_match_iter_typed(regex, result_type=str, default='')
        return retval

    def m_src_port(self,mm_r):
        """
        """
        if mm_r['src_port_low1']:
            return mm_r['src_port_low1'] + ' ' + mm_r['src_port_high1']
        return mm_r['src_port1'] or mm_r['src_service_group1'] \

    def m_src_port_method(self,mm_r):
        if mm_r['src_port_op1']:
            return mm_r['src_port_op1']
        elif mm_r['src_port_low1'] and mm_r['src_port_high1']:
            return 'range'
        elif mm_r['src_service_group1']:
            return 'object-group'

    def m_dst_port(self,mm_r):
        """
        """
        if mm_r['dst_port_low1']:
            return mm_r['dst_port_low1'] + ' ' + mm_r['dst_port_high1']
        return mm_r['dst_port1'] or mm_r['dst_service_group1'] \

    def m_dst_port_method(self,mm_r):
        if mm_r['dst_port_op1']:
            return mm_r['dst_port_op1']
        elif mm_r['dst_port_low1'] and mm_r['dst_port_high1']:
            return 'range'
        elif mm_r['dst_service_group1']:
            return 'object-group'

    @property
    def result_dict(self):
        """Return a list of strings which represent the source and destination 
        ports."""
        retval = dict()

        for obj in self.children:
            ## Parse out 'service' and 'description' lines
            mm = _RE_SVCOBJ_CHILD.search(obj.text)
            if not (mm is None):
                mm_r = mm.groupdict()
            else:
                mm_r = dict()
            
            # service ...
            if mm_r.get('protocol1',None):
                retval['proto'] = mm_r['protocol1']
                retval['proto_method'] = 'proto'
                retval['src_port'] = self.m_src_port(mm_r)
                retval['src_port_method'] =  self.m_src_port_method(mm_r)
                retval['src_port_op'] = mm_r['src_port_op1']
                retval['src_port_low'] = mm_r['src_port_low1']
                retval['src_port_high'] = mm_r['src_port_high1']
                retval['dst_port'] = self.m_dst_port(mm_r)
                retval['dst_port_method'] = self.m_dst_port_method(mm_r)
                retval['dst_port_op'] = mm_r['dst_port_op1']
                retval['dst_port_low'] = mm_r['dst_port_low1']
                retval['dst_port_high'] = mm_r['dst_port_high1']
            # description
            elif mm_r.get('description0',None):
                retval['description'] =  mm_r['description0']
            else:
                raise NotImplementedError("Cannot parse '{0}'".format(obj.text))
        return retval

##
##-------------  ASA object group protocol
##
_RE_PROTO_GROUP_CHILD_STR = r"""(?:
(^\s+description(?P<description0>.+)$)
|(^\s+protocol-object\s+(?P<protocol1>\S+)$)
)
"""
_RE_PROTO_GROUP_CHILD = re.compile(_RE_PROTO_GROUP_CHILD_STR, re.VERBOSE)
class ASAObjGroupProtocol(BaseCfgLine):
    def __init__(self, *args, **kwargs):
        """
        """
        """Provide attributes on Cisco ASA Service groups"""
        super(ASAObjGroupProtocol, self).__init__(*args, **kwargs)
    
    def __repr__(self):
        return "<%s # %s '%s'>" % (self.classname, self.linenum, self.name)

    @classmethod
    def is_object_for(cls, line="", re=re):
        if re.search(r'^(object-group\sprotocol)', line):
            return True
        return False

    @property
    def name(self):
        retval = self.re_match_typed(r'^\s*object-group\sprotocol\s+(\S.+)$',
            result_type=str, default='')
        return retval

    @property
    def description(self):
        regex = r"(^\s+description(?P<description0>.+)$)"
        retval = self.re_match_iter_typed(regex,
            result_type=str, default='')
        return retval

    @property
    def result_dict(self):
        """Return a list of strings which represent the source and destination 
        ports."""
        retval = list()

        for obj in self.children:
            ## Parse out 'service' and 'description' lines
            mm = _RE_PROTO_GROUP_CHILD.search(obj.text)
            if not (mm is None):
                mm_r = mm.groupdict()
            else:
                mm_r = dict()
            
            # description
            if mm_r.get('description0',None):
                pass
            # protocol...
            elif mm_r.get('protocol1',None):
                retval.append(mm_r['protocol1'])
            else:
                raise NotImplementedError("Cannot parse '{0}'".format(obj.text))
        return retval

##
##-------------  ASA object-group network
##
_RE_NETOBJECT_STR = r"""(?:                         # Non-capturing parenthesis
(^\s+description(?P<description0>.+)$)
|(^\s+network-object\s+host\s+(?P<host>\S+))
|(^\s+network-object
    (?:\s+network)?
    \s+(?P<network>\d+\.\d+\.\d+\.\d+)
    \s+(?P<netmask>\d+\.\d+\.\d+\.\d+))
|(^\s+network-object\s+object\s+(?P<object>\S+))
|(^\s+group-object\s+(?P<groupobject>\S+))
)                                                   # Close non-capture parens
"""
_RE_NETOBJECT = re.compile(_RE_NETOBJECT_STR, re.VERBOSE)
class ASAObjGroupNetwork(ASACfgLine):

    def __init__(self, *args, **kwargs):
        """Accept an ASA line number and initialize family relationship
        attributes"""
        super(ASAObjGroupNetwork, self).__init__(*args, **kwargs)

    @classmethod
    def is_object_for(cls, line="", re=re):
        if re.search(r'^(?:object-group\snetwork)', line):
            return True
        return False

    @property
    def name(self):
        retval = self.re_match_typed(r'^object-group\snetwork\s+(\S.+)$',
            result_type=str, default='')
        return retval

    @property
    def description(self):
        regex = r"(^\s+description(?P<description0>.+)$)"
        retval = self.re_match_iter_typed(regex,
            result_type=str, default='')
        return retval

    @property
    def hash_children(self):
        ## Manually override the BaseCfgLine method since this recurses through
        ##    children
        ## FIXME: Implement hash_children for ASAObjGroupService
        return hash(tuple(self.network_strings))  # network_strings recurses...

    @property
    def network_count(self):
        ## Return the number of discrete network objects covered by this group
        ## FIXME: Implement port_count for ASAObjGroupService
        return len(self.network_strings)

    @property
    def network_strings(self):
        """Return a list of strings which represent the address space allowed by
        this object-group"""
        retval = list()
        names = self.confobj.names
        for obj in self.children:

            ## Parse out 'object-group ...' and 'group-object' lines...
            mm = _RE_NETOBJECT.search(obj.text)
            if not (mm is None):
                net_obj = mm.groupdict()
                if net_obj['netmask']=='255.255.255.255':
                    net_obj['host'] = net_obj['network']
            else:
                net_obj = dict()

            if net_obj.get('host', None):
                retval.append(names.get(net_obj['host'], 
                    net_obj['host']))
            elif net_obj.get('network', None):
                ## This is a non-host network object
                retval.append('{0}/{1}'.format(names.get(net_obj['network'], 
                    net_obj['network']), net_obj['netmask']))
            elif net_obj.get('groupobject', None):
                groupobject = net_obj['groupobject']
                if groupobject==self.name:
                    ## Throw an error when importing self
                    raise ValueError("FATAL: Cannot recurse through group-object {0} in object-group network {1}".format(groupobject, self.name))

                group_nets = self.confobj.object_group_network.get(groupobject,
                    None)
                if (group_nets is None):
                    raise ValueError("FATAL: Cannot find group-object named {0}".format(name))
                else:
                    retval.extend(group_nets.network_strings)
            elif 'description ' in obj.text:
                pass
            else:
                raise NotImplementedError("Cannot parse '{0}'".format(obj.text))
        return retval

    @property
    def networks(self):
        """Return a list of IPv4Obj objects which represent the address space allowed by
        This object-group"""
        ## FIXME: Implement object caching for other ASAConfigList objects
        ## Return a cached result if the networks lookup has already been done

        retval = list()
        for net_str in self.network_strings:
            ## Check the ASACfgList cache of network objects
            if not self.confobj._network_cache.get(net_str, False):
                net = IPv4Obj(net_str)
                self.confobj._network_cache[net_str] = net
                retval.append(net)
            else:
                retval.append(self.confobj._network_cache[net_str])

        return retval

    def m_network_name_exist(self,name):
        group_ports = self.confobj.object_group_network.get(name, None) \
                or self.confobj.object_network.get(name, None)
                
        if name==self.name:
            ## Throw an error when importing self
            raise ValueError('FATAL: Cannot recurse through group-object {0}'\
                             ' in object-group or object network {1}'\
                             .format(name, self.name))
        if (group_ports is None):
            return False
        return True

    @property
    def result_dict(self):
        """Return a list of objects which represent 
        the network group members"""     
        retval = list()
        for obj in self.children:
            mm = _RE_NETOBJECT.search(obj.text)
            if not (mm is None):
                mm_r = mm.groupdict()
            else:
                raise ValueError("[FATAL] models_asa cannot parse '{0}'"\
                                 .format(obj.text))
            
            net_obj = dict()
            if mm_r.get('description0',None):
                net_obj['member_method'] = 'description'
            elif mm_r.get('host', None):
                net_obj['ipaddr'] = mm_r['host']
                net_obj['mask'] = '255.255.255.255'
                net_obj['member_method'] = 'host'
            elif mm_r.get('network', None):
                net_obj['subnet'] = mm_r['network']
                net_obj['mask'] = mm_r['netmask']
                net_obj['member_method'] = 'subnet'
            elif mm_r.get('group-object', None):
                net_obj['object_name'] = mm_r['groupobject']
                net_obj['member_method'] = 'group-object'
                # Make sure the network group was defined before
                if not self.m_network_name_exist(mm_r['groupobject']):
                    raise ValueError("FATAL: Cannot find network object named {0}"\
                                     .format(name))
            elif mm_r.get('object', None):
                net_obj['object_name'] = mm_r['object']
                net_obj['member_method'] = 'object'
                # Make sure the network object was defined before
                if not self.m_network_name_exist(mm_r['object']):
                    raise ValueError("FATAL: Cannot find network object named {0}"\
                                     .format(name))
            retval.append(net_obj)

        return retval


##
##-------------  ASA object-group service
##
# Difference between service-object and port-object
#
# object-group service WEB-PORTS tcp        <- proto is here
#   port-object eq www
#   port-object eq https
#
#  object-group service WEB-PORTS
#    service-object tcp eq 80               <- proto is here
#    service-object tcp eq 443              <- proto is here
#
_RE_SVCGROUP_CHILD_STR = r"""(?:                    # Non-capturing parentesis
# TODO: Add support for source ports in this regex
# Examples                                  group_suffix
#   service-object icmp|ip|tcp|udp|..       1
#   service-object udp destination eq dns   2
#   service-object tcp eq 80                2
#   service-object tcp range 5000 5005      3
#   service-object object TCP_4443          4
#   port-object eq https                    5
#   port-object range 1 1024                6
#   group-object RPC_High_ports_TCP         7
#   icmp-object echo-reply|time-exceeded|.. 8
#
(^\s+description\s+(?P<description0>.*)$)
|(^\s+service-object\s+(?P<protocol1>{3})$)
|(^\s+service-object\s+(?P<protocol2>{0})(?:\s+destination)?
    \s+(?P<dst_port_op2>{1})\s+(?P<dst_port2>{2}))
|(^\s+service-object\s+(?P<protocol3>{0})(?:\s+destination)?
    \s+(?P<dst_port_op3>range)\s+(?P<dst_port_low3>\d+)\s+(?P<dst_port_high3>\d+))
|(^\s+service-object\sobject\s+(?P<dst_object4>\S+))
|(^\s+port-object\s+(?P<dst_port_op5>{1})\s+(?P<dst_port5>{2}))
|(^\s+port-object\s+(?P<dst_port_op6>range)
    \s+(?P<dst_port_low6>\d+)\s+(?P<dst_port_high6>\d+))
|(^\s+group-object\s+(?P<dst_group7>\S+))
|(^\s+icmp-object\s+(?P<dst_icmp_msg8>\S+))
)                                                   # Close non-capture parens
""".format(_IP_PROTO,_PORT_SIMPLE_OP,_PORT_NAMES,_ALL_PROTOCOLS)
_RE_SVCGROUP_CHILD = re.compile(_RE_SVCGROUP_CHILD_STR, re.VERBOSE)
class ASAObjGroupService(BaseCfgLine):
    def __init__(self, *args, **kwargs):
        """
        """
        """Provide attributes on Cisco ASA Service groups"""
        super(ASAObjGroupService, self).__init__(*args, **kwargs)
    
    def __repr__(self):
        return "<%s # %s '%s'>" % (self.classname, self.linenum, self.name)

    @classmethod
    def is_object_for(cls, line="", re=re):
        if re.search(r'^(?:object-group\sservice)', line):
            return True
        return False

    @property
    def name(self):
        retval = self.re_match_typed(r'object-group\s+service\s+(\S+)\s*.*$',
            result_type=str, default='')
        return retval

    @property
    def description(self):
        retval = self.re_match_iter_typed(r'\s+description\s+(\S+)$',
            result_type=str, default='')
        return retval

    @property
    def proto(self):
        retval = self.re_match(r'object-group\s+service\s+(?:\S+)\s+(\S+)?$',
            group=1, default=None)
        return retval

    def m_proto(self,mm_r):
        """
        """
        return mm_r['protocol1'] or mm_r['protocol2'] or mm_r['protocol3'] \
            or self.proto

    def m_proto_method(self,mm_r):
        if mm_r['protocol1']:
            return 'protocol'
        elif mm_r['protocol2'] or mm_r['protocol3']:
            return 'service-object'
        elif mm_r['dst_group7']:
            return 'group'
        elif mm_r['dst_object4']:
            return 'object'
        elif mm_r['dst_icmp_msg8']:
            return 'icmp'
        elif self.proto:
            return 'port-object'

    def m_dst_port(self,mm_r):
        if mm_r['dst_port_op3']:
            return mm_r['dst_port_low3'] + ' ' + mm_r['dst_port_high3']
        elif mm_r['dst_port_op6']:
            return mm_r['dst_port_low6'] + ' ' + mm_r['dst_port_high6']
        return mm_r['dst_port2'] or mm_r['dst_port5'] \
            or mm_r['dst_object4'] or mm_r['dst_group7'] or mm_r['dst_icmp_msg8']

    def m_dst_port_method(self,mm_r):
        if mm_r['dst_port_op2']:
            return mm_r['dst_port_op2']
        elif mm_r['dst_port_op5']:
            return mm_r['dst_port_op5']
        elif (mm_r['dst_port_low3'] and mm_r['dst_port_high3'])\
                or (mm_r['dst_port_low6'] and mm_r['dst_port_high6']):
            return 'range'
        elif mm_r['dst_object4']:
            return 'object'
        elif mm_r['dst_group7']:
            return 'group'
        elif mm_r['dst_icmp_msg8']:
            return 'icmp'

    def m_dst_port_op(self,mm_r):
        return mm_r['dst_port_op2'] or mm_r['dst_port_op3'] \
                or mm_r['dst_port_op5'] or mm_r['dst_port_op6']

    def m_service_name_exist(self,name):
        group_ports = self.confobj.object_group_service.get(name, None) \
                or self.confobj.object_service.get(name, None)
                
        if name==self.name:
            ## Throw an error when importing self
            raise ValueError("FATAL: Cannot recurse through group-object {0} in object-group service {1}".format(name, self.name))
        if (group_ports is None):
            return False
        return True

    @property
    def result_dict(self):
        """
        Return a list of objects which represent the protocol and ports 
        allowed by this object-group
        """
        retval = list()
        for obj in self.children:
            mm = _RE_SVCGROUP_CHILD.search(obj.text)
            if not (mm is None):
                mm_r = mm.groupdict()
            else:
                raise ValueError("[FATAL] models_asa cannot parse '{0}'"\
                                 .format(obj.text))
            
            if mm_r.get('description0',None):
                pass
            else:
                svc = dict()
                svc['proto'] = self.m_proto(mm_r)
                svc['proto_method'] = self.m_proto_method(mm_r)
                svc['dst_port'] = self.m_dst_port(mm_r)
                svc['dst_port_method'] = self.m_dst_port_method(mm_r)
                svc['dst_port_op'] = self.m_dst_port_op(mm_r)
                svc['dst_port_low'] = mm_r['dst_port_low3'] or mm_r['dst_port_low6']
                svc['dst_port_high'] = mm_r['dst_port_high3'] or mm_r['dst_port_low6']
        
                # Make sure the service group was defined before
                if self.m_dst_port_method(mm_r) in ['object','group']:
                    name = self.m_dst_port(mm_r)
                    if not self.m_service_name_exist(name):
                        raise ValueError("FATAL: Cannot find service object named {0}"\
                                         .format(name))

                retval.append(svc)

        return retval

##
##-------------  ASA Interface Object
##

class ASAIntfLine(BaseASAIntfLine):

    def __init__(self, *args, **kwargs):
        """Accept an ASA line number and initialize family relationship
        attributes"""
        super(ASAIntfLine, self).__init__(*args, **kwargs)

    @classmethod
    def is_object_for(cls, line="", re=re):
        intf_regex = r'^interface\s+(\S+.+)'
        if re.search(intf_regex, line):
            return True
        return False

##
##-------------  ASA Interface Globals
##

class ASAIntfGlobal(BaseCfgLine):
    def __init__(self, *args, **kwargs):
        super(ASAIntfGlobal, self).__init__(*args, **kwargs)
        self.feature = 'interface global'

    def __repr__(self):
        return "<%s # %s '%s'>" % (self.classname, self.linenum, 
            self.text)

    @classmethod
    def is_object_for(cls, line="", re=re):
        if re.search('^mtu', line):
            return True
        return False


##
##-------------  ASA Hostname Line
##

class ASAHostnameLine(BaseCfgLine):
    def __init__(self, *args, **kwargs):
        super(ASAHostnameLine, self).__init__(*args, **kwargs)
        self.feature = 'hostname'

    def __repr__(self):
        return "<%s # %s '%s'>" % (self.classname, self.linenum, 
            self.hostname)

    @classmethod
    def is_object_for(cls, line="", re=re):
        if re.search('^hostname', line):
            return True
        return False

    @property
    def hostname(self):
        retval = self.re_match_typed(r'^hostname\s+(\S+)',
            result_type=str, default='')
        return retval


##
##-------------  Base ASA Route line object
##

class BaseASARouteLine(BaseCfgLine):
    def __init__(self, *args, **kwargs):
        super(BaseASARouteLine, self).__init__(*args, **kwargs)

    def __repr__(self):
        return "<%s # %s '%s' info: '%s'>" % (self.classname, self.linenum, self.network_object, self.routeinfo)

    @property
    def routeinfo(self):
        ### Route information for the repr string
        if self.tracking_object_name:
            return self.nexthop_str+" AD: "+str(self.admin_distance)+" Track: "+self.tracking_object_name
        else:
            return self.nexthop_str+" AD: "+str(self.admin_distance)

    @classmethod
    def is_object_for(cls, line="", re=re):
        return False

    @property
    def address_family(self):
        ## ipv4, ipv6, etc
        raise NotImplementedError

    @property
    def network(self):
        raise NotImplementedError

    @property
    def netmask(self):
        raise NotImplementedError

    @property
    def admin_distance(self):
        raise NotImplementedError

    @property
    def nexthop_str(self):
        raise NotImplementedError

    @property
    def tracking_object_name(self):
        raise NotImplementedError

##
##-------------  ASA Configuration line object
##

class ASARouteLine(BaseASARouteLine):
    def __init__(self, *args, **kwargs):
        super(ASARouteLine, self).__init__(*args, **kwargs)
        if 'ipv6' in self.text:
            self.feature = 'ipv6 route'
        else:
            self.feature = 'ip route'

    @classmethod
    def is_object_for(cls, line="", re=re):
        if re.search('^(ip|ipv6)\s+route\s+\S', line):
            return True
        return False

    @property
    def address_family(self):
        ## ipv4, ipv6, etc
        retval = self.re_match_typed(r'^(ip|ipv6)\s+route\s+*(\S+)',
            group=1, result_type=str, default='')
        return retval

    @property
    def network(self):
        if self.address_family=='ip':
            retval = self.re_match_typed(r'^ip\s+route\s+*(\S+)',
                group=2, result_type=str, default='')
        elif self.address_family=='ipv6':
            retval = self.re_match_typed(r'^ipv6\s+route\s+*(\S+?)\/\d+',
                group=2, result_type=str, default='')
        return retval

    @property
    def netmask(self):
        if self.address_family=='ip':
            retval = self.re_match_typed(r'^ip\s+route\s+*\S+\s+(\S+)',
                group=2, result_type=str, default='')
        elif self.address_family=='ipv6':
            retval = self.re_match_typed(r'^ipv6\s+route\s+*\S+?\/(\d+)',
                group=2, result_type=str, default='')
        return retval

    @property
    def network_object(self):
        try:
            if self.address_family=='ip':
                return IPv4Obj('%s/%s' % (self.network, self.netmask), 
                    strict=False)
            elif self.address_family=='ipv6':
                return IPv6Network('%s/%s' % (self.network, self.netmask))
        except:
            return None

    @property
    def nexthop_str(self):
        if self.address_family=='ip':
            retval = self.re_match_typed(r'^ip\s+route\s+*\S+\s+\S+\s+(\S+)',
                group=2, result_type=str, default='')
        elif self.address_family=='ipv6':
            retval = self.re_match_typed(r'^ipv6\s+route\s+*\S+\s+(\S+)',
                group=2, result_type=str, default='')
        return retval

    @property
    def admin_distance(self):
        retval = self.re_match_typed(r'(\d+)$',
            group=1, result_type=int, default=1)
        return retval


    @property
    def tracking_object_name(self):
        retval = self.re_match_typed(r'^ip(v6)*\s+route\s+.+?track\s+(\S+)',
            group=2, result_type=str, default='')
        return retval

# Updated the ports as the original were incomplete.
#_ACL_PROTOCOLS = 'ip|tcp|udp|ah|eigrp|esp|gre|igmp|igrp|ipinip|ipsec|ospf|pcp|pim|pptp|snp|\d+'
#_ACL_ICMP_PROTOCOLS = 'alternate-address|conversion-error|echo-reply|echo|information-reply|information-request|mask-reply|mask-request|mobile-redirect|parameter-problem|redirect|router-advertisement|router-solicitation|source-quench|time-exceeded|timestamp-reply|timestamp-request|traceroute|unreachable'
#_ACL_LOGLEVELS = r'alerts|critical|debugging|emergencies|errors|informational|notifications|warnings|[0-7]'

_ACL_PROTOCOLS = 'ip|tcp|udp|ahp|ah|eigrp|esp|gre|igmp|igrp|ipinip|ipsec'\
                '|ospf|pcp|pim|pptp|snp|\d+'
_ACL_ICMP_PROTOCOLS = 'alternate-address|conversion-error|echo-reply|echo'\
                '|information-reply|information-request|mask-reply'\
                '|mask-request|mobile-redirect|parameter-problem|redirect'\
                '|router-advertisement|router-solicitation|source-quench'\
                '|time-exceeded|timestamp-reply|timestamp-request|traceroute'\
                '|unreachable'
_ACL_LOGLEVELS = r'alerts|critical|debugging|emergencies|errors'\
                '|informational|notifications|warnings|[0-7]'
_ACL_PORT_NAMES = r'aol|bgp|chargen|cifs|citrix-ica|cmd|ctiqbe|daytime'\
                '|discard|domain|echo|exec|finger|tftp|ftp|ftp-data|gopher'\
                '|h323|hostname|http|https|ident|imap4|irc|kerberos|klogin'\
                '|kshell|ldap|ldaps|login|lotusnotes|lpd|netbios-ssn|nfs'\
                '|nntp|ntp|pcanywhere-data|pim-auto-rp|pop2|pop3|pptp|rsh'\
                '|rtsp|sip|smtp|sqlnet|ssh|sunrpc|tacacs|talk|telnet|uucp'\
                '|whois|www|netbios-ns|netbios-dgm|netbios-ss|snmptrap|snmp'\
                '|syslog|isakmp|bootps|bootpc|\d+'
_RE_ACLOBJECT_STR = r"""(?:                         # Non-capturing parenthesis
# remark
(^access-list\s+(?P<name0>\S+)\s+(?P<type0>remark)\s+(?P<remark>.*)$)

# extended service object with source network object, destination network object
|(?:^access-list\s+(?P<name1>\S+)
 \s+(?P<type1>extended)
 \s+(?P<action1>permit|deny)
 \s+(?:                        # proto
     (?:object-group\s+(?P<service_objectgroup1>\S+))
    |(?:object\s+(?P<service_object1>\S+))
    |(?P<protocol1>{0})
 )
 \s+(?:                        # source addr
    (?P<src_any1>any|any4|any6)
    |(?:object-group\s+(?P<src_objectgroup1>\S+))
    |(?:object\s+(?P<src_object1>\S+))
    |(?:host\s+(?P<src_host1a>\S+))
    |(?:(?P<src_host1b>\S+)\s+0\.0\.0\.0)
    |(?:(?P<src_network1>\S+)\s+(?P<src_hostmask1>\d+\.\d+\.\d+\.\d+))
 )
 \s+(?:                       # destination addr
    (?P<dst_any1>any|any4|any6)
    |(?:object-group\s+(?P<dst_objectgroup1>\S+))
    |(?:object\s+(?P<dst_object1>\S+))
    |(?:host\s+(?P<dst_host1a>\S+))
    |(?:(?P<dst_host1b>\S+)\s+0\.0\.0\.0)
    |(?:(?P<dst_network1>\S+)\s+(?P<dst_hostmask1>\d+\.\d+\.\d+\.\d+))
 )
 (?:\s+
   (?:                         # destination port
     (?:
        (?P<dst_port_op1>eq|neq|lt|gt)
        \s(?P<dst_port1>(?:(?:{3})\s?)+)
     )
     |(?:range\s+(?P<dst_port_low1>\S+)\s+(?P<dst_port_high1>\S+))
     |(?:object-group\s+(?P<dst_service_group1>\S+))
   )
 )?
 (?:\s+
    (?P<log1>log)
    (?:\s+(?P<loglevel1>{1}))?
    (?:\s+interval\s+(?P<log_interval1>\d+))?
 )?
 (?:\s+(?P<disable1>disable))?
 (?:
   (?:\s+(?P<inactive1>inactive))
   |(?:\s+time-range\s+(?P<time_range1>\S+))
 )?
\s*$)    # END access-list 1 parse

#access-list TESTME extended permit icmp any4 0.0.0.0 0.0.0.0 unreachable log interval 1
|(?:^access-list\s+(?P<name2>\S+)
 \s+(?P<type2>extended)
 \s+(?P<action2>permit|deny)
 \s+(?P<protocol2>icmp)
 \s+(?:                        # source addr
    (?P<src_any2>any|any4|any6)
    |(?:object-group\s+(?P<src_objectgroup2>\S+))
    |(?:object\s+(?P<src_object2>\S+))
    |(?:host\s+(?P<src_host2a>\S+))
    |(?:(?P<src_host2b>\S+)\s+0\.0\.0\.0)
    |(?:(?P<src_network2>\S+)\s+(?P<src_hostmask2>\d+\.\d+\.\d+\.\d+))
 )
 \s+(?:                       # destination addr
    (?P<dst_any2>any|any4|any6)
    |(?:object-group\s+(?P<dst_objectgroup2>\S+))
    |(?:object\s+(?P<dst_object2>\S+))
    |(?:host\s+(?P<dst_host2a>\S+))
    |(?:(?P<dst_host2b>\S+)\s+0\.0\.0\.0)
    |(?:(?P<dst_network2>\S+)\s+(?P<dst_hostmask2>\d+\.\d+\.\d+\.\d+))
 )
 (?:\s+(?P<icmp_proto2>{3}|\d+))?
 (?:\s+
    (?P<log2>log)
    (?:\s+(?P<loglevel2>{1}))?
    (?:\s+interval\s+(?P<log_interval2>\d+))?
 )?
 (?:\s+(?P<disable2>disable))?
 (?:
    (?:\s+(?P<inactive2>inactive))
   |(?:\s+time-range\s+(?P<time_range2>\S+))
 )?
)

# access-list SPLIT_TUNNEL_NETS standard permit 192.0.2.0 255.255.255.0
|(?:^access-list\s+(?P<name3>\S+)
 \s+(?P<type3>standard)
 \s+(?P<action3>permit|deny)
 \s+(?:                       # destination addr
    (?P<dst_any3>any|any4|any6)
    |(?:object-group\s+(?P<dst_objectgroup3>\S+))
    |(?:object\s+(?P<dst_object3>\S+))
    |(?:host\s+(?P<dst_host3a>\S+))
    |(?:(?P<dst_host3b>\S+)\s+0\.0\.0\.0)
    |(?:(?P<dst_host3c>\S+))
    |(?:(?P<dst_network3>\S+)\s+(?P<dst_hostmask3>\d+\.\d+\.\d+\.\d+))
 )
 (?:\s+
    (?P<log3>log)
    (?:\s+(?P<loglevel3>{2}))?
    (?:\s+interval\s+(?P<log_interval3>\d+))?
 )?
 (?:\s+(?P<disable3>disable))?
 (?:
    (?:\s+(?P<inactive3>inactive))
   |(?:\s+time-range\s+(?P<time_range3>\S+))
 )?
)
)                                                   # Close non-capture parens
""".format(_ACL_PROTOCOLS, _ACL_LOGLEVELS, _ACL_ICMP_PROTOCOLS, _ACL_PORT_NAMES)
_RE_ACLOBJECT = re.compile(_RE_ACLOBJECT_STR, re.VERBOSE)

class ASAAclLine(ASACfgLine):

    def __init__(self, *args, **kwargs):
        """Provide attributes on Cisco ASA Access-Lists"""
        super(ASAAclLine, self).__init__(*args, **kwargs)
        mm = _RE_ACLOBJECT.search(self.text)
        if not (mm is None):
            self._mm_results = mm.groupdict()   # All regex match results
        else:
            raise ValueError("[FATAL] models_asa cannot parse '{0}'".format(self.text))

    @classmethod
    def is_object_for(cls, line="", re=re):
        if re.search('^access-list', line):
            return True
        return False

    @property
    def name(self):
        mm_r = self._mm_results
        return mm_r['name0'] or mm_r['name1'] or mm_r['name2'] \
                or mm_r['name3']

    @property
    def type(self):
        mm_r = self._mm_results
        return mm_r['type0'] or mm_r['type1'] or mm_r['type2'] or mm_r['type3']

    @property
    def action(self):
        mm_r = self._mm_results
        return mm_r['action1'] or mm_r['action2'] or mm_r['action3']

    @property
    def remark(self):
        mm_r = self._mm_results
        return mm_r['remark']

    @property
    def proto(self):
        """
        \s+(?:
           (?:object-group\s+(?P<service_object1>\S+))
          |(?P<protocol1>{0})
        )
        """
        mm_r = self._mm_results
        return mm_r['service_objectgroup1'] or mm_r['service_object1'] \
                or mm_r['protocol1'] or mm_r['protocol2']

    @property
    def proto_method(self):
        mm_r = self._mm_results
        if mm_r['protocol1'] or mm_r['protocol2']:
            return 'proto'
        elif mm_r['service_objectgroup1'] or mm_r['service_object1']:
            return 'object-group'
        elif self.action == 'remark':
            return 'remark'

    @property
    def src_addr(self):
        """
         (?P<src_any0>any|any4|any6)
        |(?:object-group\s+(?P<src_objectgroup0>\S+))
        |(?:object\s+(?P<src_object0>\S+))
        |(?:host\s+(?P<src_host0a>\S+))
        |(?:(?P<src_host0b>\S+)\s+0\.0\.0\.0\)
        |(?:(?P<src_network0>\S+)\s+(?P<src_hostmask0>\d+\.\d+\.\d+\.\d+))
        """
        mm_r = self._mm_results
        return mm_r['src_any1'] or mm_r['src_objectgroup1'] \
                or mm_r['src_object1'] or mm_r['src_host1a'] \
                or mm_r['src_host1b'] \
                or mm_r['src_network1'] \
                \
                or mm_r['src_any2'] or mm_r['src_objectgroup2'] \
                or mm_r['src_object2'] or mm_r['src_host2a'] \
                or mm_r['src_host2b'] \
                or mm_r['src_network2']

    @property
    def src_hostmask(self):
        mm_r = self._mm_results
        method = self.src_addr_method
        if method == 'any':
            return '255.255.255.255'
        elif method == 'host':
            return '0.0.0.0'
        elif method == 'network':
            return  mm_r['src_hostmask1'] or mm_r['src_hostmask2']
        elif method == 'object-group' or method == 'object' \
                or method == 'remark' \
                or self.parent.type == 'standard': # standard acl = no src ip
            return None

    @property
    def src_addr_method(self):
        mm_r = self._mm_results
        if mm_r['src_any1'] or mm_r['src_any2']:
            return 'any'
        elif mm_r['src_objectgroup1'] or mm_r['src_objectgroup2']:
            return 'object-group'
        elif mm_r['src_object1'] or mm_r['src_object2']:
            return 'object'
        elif mm_r['src_host1a'] or mm_r['src_host1b'] \
                or mm_r['src_host2a'] or mm_r['src_host2b']:
            return 'host'
        elif (mm_r['src_network1'] or mm_r['src_hostmask1']) \
                or (mm_r['src_network2'] or mm_r['src_hostmask2']):
            return 'network'
        elif self.action == 'remark':
            return 'remark'
        elif self.parent.type == 'standard':    # standard acl = no src ip
            return None

    @property
    def src_port(self):
        return None

    @property
    def src_port_method(self):
        return None

    @property
    def dst_addr(self):
        """ (dst start at position 1)
         (?P<dst_any1>any|any4|any6)
        |(?:object-group\s+(?P<dst_objectgroup1>\S+))
        |(?:object\s+(?P<dst_object1>\S+))
        |(?:host\s+(?P<dst_host1a>\S+))
        |(?:(?P<dst_host1b>\S+)\s+0\.0\.0\.0\)
        |(?:(?P<dst_network1>\S+)\s+(?P<dst_hostmask1>\d+\.\d+\.\d+\.\d+))
        """
        mm_r = self._mm_results
        return mm_r['dst_any1'] or mm_r['dst_objectgroup1'] \
                or mm_r['dst_object1'] or mm_r['dst_host1a'] \
                or mm_r['dst_host1b'] \
                or mm_r['dst_network1'] \
                \
                or mm_r['dst_any2'] or mm_r['dst_objectgroup2'] \
                or mm_r['dst_object2'] or mm_r['dst_host2a'] \
                or mm_r['dst_host2b'] \
                or mm_r['dst_network2'] \
                \
                or mm_r['dst_any3'] or mm_r['dst_objectgroup3'] \
                or mm_r['dst_object3'] or mm_r['dst_host3a'] \
                or mm_r['dst_host3b'] or mm_r['dst_host3c']\
                or mm_r['dst_network3']

    @property
    def dst_hostmask(self):
        mm_r = self._mm_results
        method = self.dst_addr_method
        if method == 'any':
            return '255.255.255.255'
        elif method == 'host':
            return '0.0.0.0'
        elif method == 'network':
            return mm_r['dst_hostmask1'] or mm_r['dst_hostmask2'] \
                    or mm_r['dst_hostmask3']
        elif method == 'object-group' or method == 'object' \
                or method == 'remark':
            return None
        else:
            return None

    @property
    def dst_addr_method(self):
        mm_r = self._mm_results
        if mm_r['dst_any1'] or mm_r['dst_any2'] or mm_r['dst_any3']:
            return 'any'
        elif mm_r['dst_objectgroup1'] or mm_r['dst_objectgroup2'] \
                or mm_r['dst_objectgroup3']:
            return 'object-group'
        elif mm_r['dst_object1'] or mm_r['dst_object2'] or mm_r['dst_object3']:
            return 'object'
        elif mm_r['dst_host1a'] or mm_r['dst_host1b'] \
                or mm_r['dst_host2a'] or mm_r['dst_host2b'] \
                or mm_r['dst_host3a'] or mm_r['dst_host3b'] \
                or mm_r['dst_host3c']:
            return 'host'
        elif (mm_r['dst_network1'] and mm_r['dst_hostmask1']) \
                or (mm_r['dst_network2'] and mm_r['dst_hostmask2']) \
                or (mm_r['dst_network3'] and mm_r['dst_hostmask3']):
            return 'network'
        elif self.action == 'remark':
            return 'remark'
        else:
            return None

    @property
    def dst_port(self):
        """
        (?:(?P<dst_port_op1>eq|neq|lt|gt)\s+(?P<dst_port1>\S+))
        |(?:range\s+(?P<dst_port_low1>\S+)\s+(?P<dst_port_high1>\S+))
        |(?:object-group\s+(?P<dst_service_group1>\S+))
        """
        mm_r = self._mm_results
        if self.dst_port_method == 'range':
            return mm_r['dst_port_low1'] + ' ' + mm_r['dst_port_high1']
        return mm_r['dst_port1'] or mm_r['dst_service_group1']

    @property
    def dst_port_method(self):
        mm_r = self._mm_results
        if mm_r['dst_port_op1']:
            return mm_r['dst_port_op1']
        elif mm_r['dst_port_low1'] and mm_r['dst_port_high1']:
            return 'range'
        elif mm_r['dst_service_group1']:
            return 'object-group'

#  (?:\s+
#    (?P<log1>log)
#    (?:\s+(?P<log_level1>{1}))?
#    (?:\s+interval\s+(?P<log_interval1>\d+))?
#  )?
#  (?:\s+(?P<disable1>disable))?
#  (?:
#    (?:\s+(?P<inactive1>inactive))
#   |(?:\s+time-range\s+(?P<time_range1>\S+))
#  )?
#  (?:\s+(?P<established>established))?     # established = temporary hack.
    @property
    def log(self):
        mm_r = self._mm_results
        return mm_r['log1'] or mm_r['log2']

    @property
    def log_level(self):
        mm_r = self._mm_results
        return mm_r['log_level1'] or mm_r['log_level2']

    @property
    def log_interval(self):
        mm_r = self._mm_results
        return mm_r['log_interval1'] or mm_r['log_interval2']

    @property
    def disable(self):
        mm_r = self._mm_results
        return mm_r['disable1'] or mm_r['disable2']

    @property
    def inactive(self):
        mm_r = self._mm_results
        return mm_r['inactive1'] or mm_r['inactive2']

    @property
    def time_range(self):
        mm_r = self._mm_results
        return mm_r['time_range1'] or mm_r['time_range2']

    # TODO: This should not be needed
    # Otherwise: fix code to support this attribute.
    @property
    def established(self):
        mm_r = self._mm_results
        return mm_r['established']
