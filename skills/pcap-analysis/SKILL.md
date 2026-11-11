---
name: pcap-analysis
description: "Analyze network captures (pcap) with Wireshark, tshark or scapy: follow streams, find suspicious traffic, extract files and credentials."
---

# Pcap Analysis

Analyze network captures (pcap) with Wireshark, tshark or scapy: follow streams, find suspicious traffic, extract files and credentials.

## Overview

Statistics > Conversations and Protocol Hierarchy.

## Filters

http.request, dns, tcp.flags.syn==1 && tcp.flags.ack==0.

## Extract

File > Export Objects; tshark -r cap.pcap -Y http -T fields.
