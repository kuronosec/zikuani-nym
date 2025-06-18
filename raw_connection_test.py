import ssl
import socket
import json

# Step 1: Connect to nym-proxy-server (running on localhost)
sock = socket.create_connection(('127.0.0.1', 8080))

# Step 2: Wrap in TLS, since the destination is https://rpc-amoy.polygon.technology:443
context = ssl.create_default_context()
tls_sock = context.wrap_socket(sock, server_hostname="rpc-amoy.polygon.technology")

# Step 3: Send a JSON-RPC request (e.g., eth_blockNumber)
payload = {
    "jsonrpc": "2.0",
    "method": "eth_blockNumber",
    "params": [],
    "id": 1
}

request = (
    f"POST / HTTP/1.1\r\n"
    f"Host: rpc-amoy.polygon.technology\r\n"
    f"Content-Type: application/json\r\n"
    f"Content-Length: {len(json.dumps(payload))}\r\n"
    f"Connection: close\r\n\r\n"
    f"{json.dumps(payload)}"
)

tls_sock.sendall(request.encode())

# Step 4: Receive and print response
response = b""
while True:
    data = tls_sock.recv(4096)
    if not data:
        break
    response += data

print(response.decode())
tls_sock.close()
