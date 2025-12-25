#!/usr/bin/env python3
"""
LIFX Device Scanner

Scans the local network for LIFX devices using the LIFX LAN Protocol.
Sends GetService (packet 2) UDP broadcasts and listens for StateService (packet 3) responses.

Protocol documentation: https://lan.developer.lifx.com/docs/packet-contents
"""

import argparse
import ipaddress
import socket
import sys
import time

from lifx_protocol import (
    LIFX_PORT,
    STATESERVICE_TYPE,
    SERVICE_UDP,
    LIFXDevice,
    get_broadcast_address,
    generate_source_id,
    create_getservice_packet,
    parse_lifx_header,
    parse_state_service,
)


def scan_network(
    subnet: str,
    timeout: float = 2.0,
    retries: int = 3,
    port: int = LIFX_PORT,
    verbose: bool = False
) -> list[LIFXDevice]:
    """
    Scan the network for LIFX devices.
    
    Args:
        subnet: Network subnet in CIDR notation (e.g., "192.168.64.0/24")
        timeout: Time to wait for responses (seconds)
        retries: Number of broadcast attempts
        port: LIFX UDP port (default 56700)
        verbose: Print verbose output
    
    Returns:
        List of discovered LIFXDevice objects
    """
    broadcast_addr = get_broadcast_address(subnet)
    
    # Generate a random source identifier
    source = generate_source_id()
    
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Bind to any available port to receive responses
    sock.bind(('', 0))
    local_port = sock.getsockname()[1]
    
    if verbose:
        print(f"Scanning subnet: {subnet}")
        print(f"Broadcast address: {broadcast_addr}")
        print(f"Source ID: {source}")
        print(f"Listening on port: {local_port}")
        print()
    
    discovered_devices: dict[str, LIFXDevice] = {}
    
    for attempt in range(retries):
        if verbose:
            print(f"Broadcast attempt {attempt + 1}/{retries}...")
        
        # Create and send GetService packet
        packet = create_getservice_packet(source, sequence=attempt)
        
        try:
            sock.sendto(packet, (broadcast_addr, port))
        except socket.error as e:
            print(f"Error sending broadcast: {e}", file=sys.stderr)
            continue
        
        # Set timeout for receiving responses
        sock.settimeout(timeout)
        
        # Collect responses
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                remaining = end_time - time.time()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                
                data, addr = sock.recvfrom(1024)
                ip_address = addr[0]
                
                # Parse the response header
                header = parse_lifx_header(data)
                if header is None:
                    if verbose:
                        print(f"  Received invalid packet from {ip_address}")
                    continue
                
                # Check if it's a StateService response
                if header['type'] != STATESERVICE_TYPE:
                    if verbose:
                        print(f"  Received non-StateService packet (type={header['type']}) from {ip_address}")
                    continue
                
                # Parse the payload
                service_info = parse_state_service(header['payload'])
                if service_info is None:
                    if verbose:
                        print(f"  Received invalid StateService payload from {ip_address}")
                    continue
                
                service, device_port = service_info
                
                # Only care about UDP service
                if service != SERVICE_UDP:
                    if verbose:
                        print(f"  Received non-UDP service ({service}) from {ip_address}")
                    continue
                
                # Create device entry using serial as unique key
                serial = header['serial']
                device_key = serial
                
                if device_key not in discovered_devices:
                    device = LIFXDevice(
                        ip_address=ip_address,
                        port=device_port,
                        serial=serial,
                        service=service
                    )
                    discovered_devices[device_key] = device
                    
                    if verbose:
                        print(f"  Found: {device}")
                
            except socket.timeout:
                break
            except socket.error as e:
                if verbose:
                    print(f"  Socket error: {e}")
                break
    
    sock.close()
    return list(discovered_devices.values())


def main():
    parser = argparse.ArgumentParser(
        description='Scan local network for LIFX devices using the LAN protocol.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Scan default subnet 192.168.64.0/24
  %(prog)s -s 192.168.1.0/24        # Scan specific subnet
  %(prog)s -s 10.0.0.0/16 -t 5      # Scan with 5 second timeout
  %(prog)s -v                       # Verbose output
        """
    )
    
    parser.add_argument(
        '-s', '--subnet',
        default='192.168.64.0/24',
        help='Network subnet to scan in CIDR notation (default: 192.168.64.0/24)'
    )
    
    parser.add_argument(
        '-t', '--timeout',
        type=float,
        default=2.0,
        help='Timeout in seconds to wait for responses (default: 2.0)'
    )
    
    parser.add_argument(
        '-r', '--retries',
        type=int,
        default=3,
        help='Number of broadcast attempts (default: 3)'
    )
    
    parser.add_argument(
        '-p', '--port',
        type=int,
        default=LIFX_PORT,
        help=f'LIFX UDP port (default: {LIFX_PORT})'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results in JSON format'
    )
    
    args = parser.parse_args()
    
    # Validate subnet
    try:
        ipaddress.ip_network(args.subnet, strict=False)
    except ValueError as e:
        print(f"Invalid subnet: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Scan the network
    if not args.json:
        print(f"Scanning for LIFX devices on {args.subnet}...")
        print()
    
    devices = scan_network(
        subnet=args.subnet,
        timeout=args.timeout,
        retries=args.retries,
        port=args.port,
        verbose=args.verbose
    )
    
    # Output results
    if args.json:
        import json
        result = {
            'subnet': args.subnet,
            'devices': [
                {
                    'ip_address': d.ip_address,
                    'port': d.port,
                    'serial': d.serial,
                    'service': d.service
                }
                for d in devices
            ]
        }
        print(json.dumps(result, indent=2))
    else:
        if devices:
            print(f"Found {len(devices)} LIFX device(s):")
            print("-" * 60)
            for device in sorted(devices, key=lambda d: d.ip_address):
                print(f"  Serial:  {device.serial}")
                print(f"  IP:      {device.ip_address}")
                print(f"  Port:    {device.port}")
                print("-" * 60)
        else:
            print("No LIFX devices found.")
            print()
            print("Troubleshooting tips:")
            print("  - Make sure your LIFX devices are powered on")
            print("  - Verify the subnet is correct for your network")
            print("  - Try increasing the timeout (-t) or retries (-r)")
            print("  - Check that UDP port 56700 is not blocked by firewall")


if __name__ == '__main__':
    main()
