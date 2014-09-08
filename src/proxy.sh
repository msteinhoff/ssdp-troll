#!/bin/bash
LOCAIF=$1
LOCAIP=$2
UPNPIP=$3

echo "1" > /proc/sys/net/ipv4/ip_forward
iptables -t nat -A PREROUTING -p tcp -d $LOCAIP --dport 7522 -j DNAT --to-destination $UPNPIP:7522
iptables -t nat -A PREROUTING -p tcp -d $LOCAIP --dport 8889 -j DNAT --to-destination $UPNPIP:8889
iptables -t nat -A POSTROUTING -o $LOCAIF -j MASQUERADE

