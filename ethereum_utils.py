from web3 import Web3
from web3.providers.base import JSONBaseProvider

import json
import os
import time
import requests
import socket
import ssl
import re

class NymHTTPProvider(JSONBaseProvider):
    def __init__(self, upstream_host, proxy_host='127.0.0.1', proxy_port=8080, timeout=50):
        self.upstream_host = upstream_host
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.timeout = timeout

    def _decode_chunked_http(self, body_bytes):
        decoded = b""
        while body_bytes:
            # Get the chunk size
            chunk_size_line, rest = body_bytes.split(b'\r\n', 1)
            chunk_size = int(chunk_size_line, 16)
            if chunk_size == 0:
                break
            chunk, body_bytes = rest[:chunk_size], rest[chunk_size + 2:]
            decoded += chunk
        return decoded

    def make_request(self, method, params):
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }
        raw_payload = json.dumps(payload)

        # Connect to nym-proxy-server
        sock = socket.create_connection((self.proxy_host, self.proxy_port), timeout=self.timeout)

        # TLS wrap with proper SNI for the upstream host
        context = ssl.create_default_context()
        tls_sock = context.wrap_socket(sock, server_hostname=self.upstream_host)

        try:
            # Send HTTPS request
            request = (
                f"POST / HTTP/1.1\r\n"
                f"Host: {self.upstream_host}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(raw_payload)}\r\n"
                f"Connection: close\r\n\r\n"
                f"{raw_payload}"
            )
            tls_sock.sendall(request.encode())

            # Read response
            response = b""
            while True:
                data = tls_sock.recv(4096)
                if not data:
                    break
                response += data
        finally:
            tls_sock.close()

        # Extract JSON from HTTP response
        body_bytes = response.split(b'\r\n\r\n', 1)[1]
        decoded_json = self._decode_chunked_http(body_bytes)
        result = json.loads(decoded_json)
        return result


class EthereumUtils:
    def __init__(self):
        # RPC provider endpoint
        provider = NymHTTPProvider(upstream_host='rpc-amoy.polygon.technology')

        self.w3 = Web3(provider)

        # Example: get latest block
        print("Current Amoy block number:")
        print(self.w3.eth.block_number)

        # Load the private key from environment variables
        self.private_key = os.getenv("ETHEREUM_ADDRESS_PRIVATE_KEY")
        if self.private_key is None:
            raise ValueError(
                "Private key not found. Set ETHEREUM_ADDRESS_PRIVATE_KEY in your environment."
            )

        # Get the sender's address from the private key
        account = self.w3.eth.account.from_key(self.private_key)
        self.sender_address = account.address

        self.w3.eth.default_account = self.sender_address

        self.user_id = self.sender_address

        if self.w3.is_connected():
            print("Connected to the Polygon Amoy testing network")
        else:
            print("Failed to connect")

        self.medical_certificate_issuer_contract = None
        self.firma_digital_credential_issuer_contract = None

    def load_contracts(self):
        # Contract address (replace with the actual address of your contract)
        medical_certificate_issuer = "0x160567b3BEAf67835D99064dcECD11a32c6AcA75"
        firma_digital_credential_issuer = "0xAa7e4806f594090b67cb319A864261543B883b87"

        medical_certificate_issuer_abi = None
        firma_digital_credential_issuer_abi = None

        # Load the ABIs from the JSON files
        with open("../../zk-firma-digital/contracts/artifacts/src/MedicalCertificateIssuer.sol/MedicalCertificateIssuer.json", "r") as abi_file:
            medical_certificate_issuer_abi = json.load(abi_file)
        with open("../../zk-firma-digital/contracts/artifacts/src/ZKFirmaDigitalCredentialIssuer.sol/ZKFirmaDigitalCredentialIssuer.json", "r") as abi_file:
            firma_digital_credential_issuer_abi = json.load(abi_file)

        # Load the contract
        self.medical_certificate_issuer_contract = self.w3.eth.contract(
            address=medical_certificate_issuer,
            abi=medical_certificate_issuer_abi["abi"]
        )
        self.firma_digital_credential_issuer_contract = self.w3.eth.contract(
            address=firma_digital_credential_issuer,
            abi=firma_digital_credential_issuer_abi["abi"]
        )

        print("Constracts loaded...")


    def create_verifiable_credential(self, verifiable_credential_path):
        print("Calling create_verifiable_credential...")
        # Load the offline verifiable credential
        with open(verifiable_credential_path, "r") as json_file:
            verifiable_credential = json.load(json_file)
        proof = self.pack_groth16_proof(verifiable_credential["proof"]["signatureValue"]["proof"])
        try:
            # Estimate gas for the transaction
            gas_estimate = self.firma_digital_credential_issuer_contract.functions.issueCredential(
                int(Web3.to_checksum_address(self.user_id), 16),
                int(verifiable_credential["proof"]["signatureValue"]["public"][3]),
                int(verifiable_credential["proof"]["signatureValue"]["public"][1]),
                int(Web3.to_checksum_address(self.user_id), 16),
                [int(verifiable_credential["proof"]["signatureValue"]["public"][2])],
                proof
            ).estimate_gas({
                'from': self.sender_address,
                'nonce': self.w3.eth.get_transaction_count(self.sender_address),
                'gasPrice': self.w3.to_wei('50', 'gwei'),
                'chainId': 80002
            })

            print("Estimated gas:", gas_estimate)
            # The order of the public data in the credential is the following
            # 0 - PublicKeyHash (Goverment public key hash)
            # 1 - Nullifier
            # 2 - Reveal Age above 18
            # 3 - NullifierSeed
            # 4 - SignalHash
            transaction = self.firma_digital_credential_issuer_contract.functions.issueCredential(
                int(Web3.to_checksum_address(self.user_id), 16),
                int(verifiable_credential["proof"]["signatureValue"]["public"][3]),
                int(verifiable_credential["proof"]["signatureValue"]["public"][1]),
                int(Web3.to_checksum_address(self.user_id), 16),
                [int(verifiable_credential["proof"]["signatureValue"]["public"][2])],
                proof
            ).build_transaction({
                'from': self.sender_address,
                'nonce': self.w3.eth.get_transaction_count(self.sender_address),
                'gas': 4000000,
                'gasPrice': self.w3.to_wei('50', 'gwei'),
                'chainId': 80002
            })

            # Sign the transaction with the private key
            signed_tx = self.w3.eth.account.sign_transaction(transaction, self.private_key)

            # Send the signed transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            # Print transaction hash
            print(f"Transaction sent! Hash: {tx_hash.hex()}")

            # Wait for the transaction receipt to confirm it was successful
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt.status == 1:
                print("Contract call succeeded!")
            else:
                print("Contract call failed.")

        except Exception as e:
            print("Error calling contract function:", e)

    def get_credentials(self):
        print("Calling get_credentials...")
        # Call the function and get the results
        try:
            credentials = self.firma_digital_credential_issuer_contract.functions.getUserCredentialIds(
                int(Web3.to_checksum_address(self.user_id), 16)
            ).call()

            credential_data, uint_array, subject_fields = self.firma_digital_credential_issuer_contract.functions.getCredential(
                int(Web3.to_checksum_address(self.user_id), 16),
                credentials[0]
            ).call()
            print(credential_data)

            return credential_data
        except Exception as e:
            print("Error calling contract function:", e)

    def create_medical_credential_request(self, encrypted_request_id):
        # Call the function and get the results
        try:
            transaction = self.medical_certificate_issuer_contract.functions.requestMedicalCertificate(
                int(Web3.to_checksum_address(self.user_id), 16),
                encrypted_request_id
            ).build_transaction({
                'from': self.sender_address,
                'nonce': self.w3.eth.get_transaction_count(self.sender_address),
                'gas': 2000000,
                'gasPrice': self.w3.to_wei('50', 'gwei'),
                'chainId': 80002
            })

            # Sign the transaction with the private key
            signed_tx = self.w3.eth.account.sign_transaction(transaction, self.private_key)

            # Send the signed transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            # Print transaction hash
            print(f"Transaction sent! Hash: {tx_hash.hex()}")

            # Wait for the transaction receipt to confirm it was successful
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt.status == 1:
                print("Contract call succeeded!")
            else:
                print("Contract call failed.")
        except Exception as e:
            print("Error calling contract function:", e)

    def get_medical_certificate_requests(self):
        # Check for new medical request from the users
        while True:
            try:
                print("Getting user request of medical certificates")
                number_requests = self.medical_certificate_issuer_contract.functions.getUserRequestCount(
                    int(Web3.to_checksum_address(self.user_id), 16)
                ).call()

                print("number_requests:" +str(number_requests))

                if int(number_requests) > 0:
                    user_request_item = self.medical_certificate_issuer_contract.functions.getUserRequest(
                        int(Web3.to_checksum_address(self.user_id), 16),
                        0
                    ).call()
                    return user_request_item
                time.sleep(600)
            except Exception as e:
                print("Error calling contract function:", e)

    def get_medical_certificate_document(self):
        # Call the function and get the results
        try:
            print("Getting created medical certificates")
            medical_certificates = self.medical_certificate_issuer_contract.functions.getGovernmentReponseCount(
                int(Web3.to_checksum_address(self.user_id), 16)
            ).call()

            if int(medical_certificates) > 0:
                medical_certificate = self.medical_certificate_issuer_contract.functions.getGovernmentReponse(
                    int(Web3.to_checksum_address(self.user_id), 16),
                    0
                ).call()
                return medical_certificate
            else:
                return None
        except Exception as e:
            print("Error calling contract function:", e)

    def respond_medical_certificate_request(self, ipfs_hash, aes_key):
        # Call the function and get the results
        try:
            # Estimate gas for the transaction
            gas_estimate = self.medical_certificate_issuer_contract.functions.respondMedicalCertificateRequest(
                int(Web3.to_checksum_address(self.user_id), 16),
                ipfs_hash,
                aes_key
            ).estimate_gas({
                'from': self.sender_address,
                'nonce': self.w3.eth.get_transaction_count(self.sender_address),
                'gasPrice': self.w3.to_wei('50', 'gwei'),
                'chainId': 80002
            })

            print("Estimated gas:", gas_estimate)

            transaction = self.medical_certificate_issuer_contract.functions.respondMedicalCertificateRequest(
                int(Web3.to_checksum_address(self.user_id), 16),
                ipfs_hash,
                aes_key
            ).build_transaction({
                'from': self.sender_address,
                'nonce': self.w3.eth.get_transaction_count(self.sender_address),
                'gas': 4000000,
                'gasPrice': self.w3.to_wei('50', 'gwei'),
                'chainId': 80002
            })

            # Sign the transaction with the private key
            signed_tx = self.w3.eth.account.sign_transaction(transaction, self.private_key)

            # Send the signed transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            # Print transaction hash
            print(f"Transaction sent! Hash: {tx_hash.hex()}")

            # Wait for the transaction receipt to confirm it was successful
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt.status == 1:
                print("Contract call succeeded!")
            else:
                print("Contract call failed.")
        except Exception as e:
            print("Error calling contract function:", e)

    def revoke_verifiable_credential(self, revocation_nonce):
        # Delete the verifiable credential when the medical certificate is delivered
        try:
            # Estimate gas for the transaction
            gas_estimate = self.firma_digital_credential_issuer_contract.functions.revokeClaimAndTransit(
                revocation_nonce
            ).estimate_gas({
                'from': self.sender_address,
                'nonce': self.w3.eth.get_transaction_count(self.sender_address),
                'gasPrice': self.w3.to_wei('50', 'gwei'),
                'chainId': 80002
            })

            print("Estimated gas:", gas_estimate)

            transaction = self.firma_digital_credential_issuer_contract.functions.revokeClaimAndTransit(
                revocation_nonce
            ).build_transaction({
                'from': self.sender_address,
                'nonce': self.w3.eth.get_transaction_count(self.sender_address),
                'gas': 4000000,
                'gasPrice': self.w3.to_wei('50', 'gwei'),
                'chainId': 80002
            })

            # Sign the transaction with the private key
            signed_tx = self.w3.eth.account.sign_transaction(transaction, self.private_key)

            # Send the signed transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            # Print transaction hash
            print(f"Transaction sent! Hash: {tx_hash.hex()}")

            # Wait for the transaction receipt to confirm it was successful
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt.status == 1:
                print("Contract call succeeded!")
            else:
                print("Contract call failed.")
        except Exception as e:
            print("Error calling contract function:", e)

    def pack_groth16_proof(self, groth16_proof):
        return [
            int(groth16_proof["pi_a"][0]),
            int(groth16_proof["pi_a"][1]),
            int(groth16_proof["pi_b"][0][1]),
            int(groth16_proof["pi_b"][0][0]),
            int(groth16_proof["pi_b"][1][1]),
            int(groth16_proof["pi_b"][1][0]),
            int(groth16_proof["pi_c"][0]),
            int(groth16_proof["pi_c"][1]),
        ]
