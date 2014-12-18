# -*- coding: utf-8 -*-
import pykka

import socket
import select
import sys
import pybonjour
import time

from mopidy import core

import logging

logger = logging.getLogger(__name__)


class AppleTvFrontend(pykka.ThreadingActor, core.CoreListener):
    def __init__(self, config, core):
        super(AppleTvFrontend, self).__init__()
        self.core = core
        self.socket = None
        
        self.resolved = []
        self.queried = []
        self.host = None
        self.timeout  = 5

        self._setup_appletv()
    
    def _setup_appletv(self):
        regtype  = "_airplay._tcp"
        browse_sdRef = pybonjour.DNSServiceBrowse(regtype = regtype,
                                          callBack = self._browse_callback)
        try:
            try:
                while not self.host:
                    ready = select.select([browse_sdRef], [], [])
                    if browse_sdRef in ready[0]:
                        pybonjour.DNSServiceProcessResult(browse_sdRef)
            except KeyboardInterrupt:
                pass
        finally:
            browse_sdRef.close()
    
    # Gets the IP from selected device
    def _query_record_callback(self, sdRef, flags, interfaceIndex, errorCode, fullname, rrtype, rrclass, rdata, ttl):
        if errorCode == pybonjour.kDNSServiceErr_NoError:
            self.host.ip = socket.inet_ntoa(rdata)
            self.queried.append(True)
    
    def _resolve_callback(self, sdRef, flags, interfaceIndex, errorCode, fullname,
                     hosttarget, port, txtRecord):
        if errorCode == pybonjour.kDNSServiceErr_NoError:
            print 'Resolved service:'
            print '  fullname   =', fullname
            print '  hosttarget =', hosttarget
            print '  port       =', port
            self.host = AirPlayDevice(interfaceIndex, fullname, hosttarget, port)
            self.resolved.append(True)
            
    def _browse_callback(self, sdRef, flags, interfaceIndex, errorCode, serviceName,
                    regtype, replyDomain):
        print "browse callback"
        if errorCode != pybonjour.kDNSServiceErr_NoError:
            return

        if not (flags & pybonjour.kDNSServiceFlagsAdd):
            print 'Service removed'
            return

        print 'Service added; resolving'

        resolve_sdRef = pybonjour.DNSServiceResolve(0,
                                                    interfaceIndex,
                                                    serviceName,
                                                    regtype,
                                                    replyDomain,
                                                    self._resolve_callback)

        try:
            while not self.resolved:
                ready = select.select([resolve_sdRef], [], [], self.timeout)
                if resolve_sdRef not in ready[0]:
                    print 'Resolve timed out'
                    break
                pybonjour.DNSServiceProcessResult(resolve_sdRef)
            else:
                self.resolved.pop()
        finally:
            resolve_sdRef.close()
            
        ####
        
        query_sdRef = pybonjour.DNSServiceQueryRecord(interfaceIndex = self.host.interfaceIndex,
                                                      fullname = self.host.hosttarget,
                                                      rrtype = pybonjour.kDNSServiceType_A,
                                                      callBack = self._query_record_callback)

        try: 
            while not self.queried:
                ready = select.select([query_sdRef], [], [], self.timeout)
                if query_sdRef not in ready[0]:
                    print "Query not in record"
                    break
                pybonjour.DNSServiceProcessResult(query_sdRef)
            else:
                self.queried.pop()
        
        finally:
            query_sdRef.close()
        

    def _post_message(self, sel_vid):
        body = "Content-Location: %s\nStart-Position: 0\n\n" % (sel_vid)
        return "POST /play HTTP/1.1\n" \
               "Content-Length: %d\n"  \
               "User-Agent: MediaControl/1.0\n\n%s" % (len(body), body)
            
        
    def track_playback_started(self, tl_track):
        logger.info('playback started')
        self._connect_to_socket(self.host.ip, self.host.port)

    def track_playback_resumed(self, tl_track, time_position):
        self._connect_to_socket(self.host.ip, self.host.port)
        
    def track_playback_paused(self, tl_track, time_position):
        pass

    def track_playback_ended(self, tl_track, time_position):
        pass

    def _connect_to_socket(self, ip, port):
        logger.info('socket connect')
        if not self.socket:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((ip, port))
        #while self.core.playback.state != self.core.PlaybackState.PLAYING:
        #    time.sleep(0.2)
        self.socket.send(self._post_message("http://192.168.1.8:8000/mopidy.mp3"))
        #while self.playing:
        #    time.sleep(1)
        #    s.send("\0")
        

class AirPlayDevice:
    def __init__(self, interfaceIndex, fullname, hosttarget, port):
        self.interfaceIndex = interfaceIndex
        self.fullname = fullname
        self.hosttarget = hosttarget
        self.port = port;
        self.displayname = hosttarget.replace(".local.", "")
        self.ip = 0
    