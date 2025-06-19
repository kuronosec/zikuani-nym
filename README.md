# zikuani-nym
Private mixnet network layer for the Zikuani wallet

# Getting started

This repo provides a PoC example of how to use the Python web3 library to connect to Ethereum Virtual Machine (EVM) compatible RPC endpoints, with the added network level privacy protection of the Nym mixnet.

## Install the Nym TcpProxy

Nym provides a couple of standalone binaries to connect appliactions to the mixing network, that you can find here: [TcpProxy binaries](https://github.com/nymtech/nym/tree/develop/sdk/rust/nym-sdk/src/tcp_proxy/bin). Take a look here of how to compile or download the binaries: [Documentation](https://nym.com/docs/developers/binaries).

## Run the nym TcpProxy commands

You have to run a couple of commands to make the TcpProxy work and be able to send and receive TCP packages to a specific Ethereum RPC endpoint (And in general to any Web site). For instance:

```bash
# Run into separate console windows

./nym-proxy-server -u rpc-amoy.polygon.technology:443

./nym-proxy-client --server-address [Replace for the address given by the former command]

```

## Clone this repo and run the main python script

Finally use the provided code in this repo to test your connection to the desired Ethereum RPC endpoint:

```bash
git clone https://github.com/kuronosec/zikuani-nym

cd zikuani-nym

# TODO: Install the required Python libraries

python main.py
```

You shoul get something like this:

```bash
python main.py                                                       
Current Amoy block number:
22995383
Connected to the Polygon Amoy testing network
Constracts loaded...
```
