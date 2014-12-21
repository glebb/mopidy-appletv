# -*- coding: utf-8 -*-
import pykka

import socket
import select
import sys
import pybonjour
import time

from mopidy import core, utils

from threading import Thread

import netifaces

import logging

import traceback

logger = logging.getLogger(__name__)


class AppleTvFrontend(pykka.ThreadingActor, core.CoreListener):
    def __init__(self, config, core):
        super(AppleTvFrontend, self).__init__()
        self.core = core
        self.socket = None
        self.running = False
        self.public_ip = netifaces.ifaddresses('wlan0')[netifaces.AF_INET][0]['addr']
        
        self.resolved = []
        self.queried = []
        self.host = None
        self.timeout  = 5

        self._setup_appletv()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._connect_socket()
    
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
        

    def _post_message(self, action, uri):
        #if not uri.startswith("mplayer:"):
        #    uri = 'http://'+self.public_ip+':8000/mopidy.mp3'
        body = "Content-Location: %s\nStart-Position: 0\n\n" % (uri)
        return "POST /"+action+" HTTP/1.1\n" \
               "Content-Length: %d\n"  \
               "User-Agent: MediaControl/1.0\n\n%s" % (len(body), body)
            
        
    def track_playback_started(self, tl_track):
        self.socket.send(self._post_message("play", tl_track.track.uri))

    def track_playback_resumed(self, tl_track, time_position):
        self.socket.send(self._post_message("rate?value=1.000000", tl_track.track.uri))
        
    def track_playback_paused(self, tl_track, time_position):
        self.socket.send(self._post_message("rate?value=0.000000", tl_track.track.uri))

    def track_playback_ended(self, tl_track, time_position):
        pass
        #self.socket.send(self._post_message("stop"))
    
    def _connect_socket(self):
        self.socket.connect((self.host.ip, self.host.port))        

    def start_thread(self):
        time.sleep(3)
        while self.running:
            try:
                self.socket.send("\0")
            except:
                logger.info("Connection to AppleTv lost. Trying to reconnect")
                self._connect_socket()
            time.sleep(2)
        utils.process.exit_process()        

    def on_start(self):
        try:
            self.running = True
            thread = Thread(target=self.start_thread)
            thread.daemon = True
            thread.start()
        except:
            traceback.print_exc()

    def on_stop(self):
        self.running = False
        

class AirPlayDevice:
    def __init__(self, interfaceIndex, fullname, hosttarget, port):
        self.interfaceIndex = interfaceIndex
        self.fullname = fullname
        self.hosttarget = hosttarget
        self.port = port;
        self.displayname = hosttarget.replace(".local.", "")
        self.ip = 0
    