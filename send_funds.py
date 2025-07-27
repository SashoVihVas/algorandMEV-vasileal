from algosdk import account, mnemonic
from algosdk.transaction import PaymentTxn
from algosdk.v2client import algod
import random
import base64
import time
import argparse  # Import the argparse library


def wait_for_confirmation_with_timeout(client, txid, timeout=1000):
    """Waits for a transaction to be confirmed with a timeout."""
    start_time = time.time()

    while True:
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout:
            print(f"Transaction confirmation timed out after {timeout} seconds")
            return None

        # Check the transaction status
        try:
            pending_txn = client.pending_transaction_info(txid)
        except Exception as e:
            print(f"Error fetching pending transaction: {e}")
            return None

        if 'confirmed-round' in pending_txn:
            return pending_txn['confirmed-round']

        time.sleep(1)  # Wait for 1 second before retrying


def send_funds(private_key, receiver_address, amount, node_address, node_token):
    """Connects to a node, builds a transaction, and sends it."""
    algod_client = algod.AlgodClient(node_token, node_address)

    public_key = account.address_from_private_key(private_key)
    print(f"Public Key: {public_key}")
    print(f"Receiver's Address: {receiver_address}")

    account_info = algod_client.account_info(public_key)
    print(f"Sender's balance before transaction: {account_info['amount']} microAlgos")

    params = algod_client.suggested_params()
    print(f"Suggested Params: {params}")

    random_note = random.randint(1, 10000)  # Generating a random integer as the note
    encoded_note = base64.b64encode(str(random_note).encode())

    txn = PaymentTxn(public_key, params, receiver_address, amount, None, note=encoded_note)
    signed_txn = txn.sign(private_key)

    txid = algod_client.send_transaction(signed_txn)
    print(f"Transaction ID: {txid}")

    try:
        confirmed_round = wait_for_confirmation_with_timeout(algod_client, txid)
        if confirmed_round:
            print(f"Transaction confirmed in round {confirmed_round}")
    except Exception as e:
        print(f"Exception raised: {e}")


def main():
    # Set up the argument parser
    parser = argparse.ArgumentParser(description="Send Algorand funds to a specified address.")

    # Add argument for the receiver's address with a default value
    parser.add_argument(
        '--receiver-address',
        type=str,
        default="56RGDWILVIFVAHQU5FQ2SDNSTPX5Y6XRKZZJYGV6PBFEW6KDUT757NPNU4",
        help="The Algorand address to send funds to."
    )

    # Add argument for the node's address with a default value
    parser.add_argument(
        '--node-address',
        type=str,
        default="http://192.168.30.2:4100",
        help="The address of the Algorand participation node."
    )

    # Parse the arguments from the command line
    args = parser.parse_args()

    # Define the other transaction parameters
    example_private_key = "UK790krMFIp90Z02KuuLk+g6O5GOnQwSBYyqqMCw/w/z03/UuY2YCWL3xuu8RXC13ybK5QauZ+2hkgh+ZM2y/A=="
    example_amount = 2000000000
    example_node_token = "97361fdc801fe9fd7f2ae87fa4ea5dc8b9b6ce7380c230eaf5494c4cb5d38d61"

    # Call the send_funds function using the parsed arguments
    send_funds(
        private_key=example_private_key,
        receiver_address=args.receiver_address,  # Use the value from command line or default
        amount=example_amount,
        node_address=args.node_address,  # Use the value from command line or default
        node_token=example_node_token
    )


if __name__ == "__main__":
    main()