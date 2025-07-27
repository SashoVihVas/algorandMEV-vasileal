import pathlib
import sys
import os
import argparse  # Import the argparse library
import time
import json
import base64
import csv
import concurrent.futures

from algosdk import mnemonic, account, transaction, abi
from algosdk.atomic_transaction_composer import (
    AtomicTransactionComposer,
    AccountTransactionSigner,
)
from algosdk.v2client import algod
from dotenv import load_dotenv

# Add the 'contract' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from playground.experiments.utils import (
    get_test_non_part_1,
    get_test_non_part_2,
)

load_dotenv()  # take environment variables from .env.


def generate_data():
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(
        description="Generate transaction data by sending concurrent method calls."
    )
    parser.add_argument(
        "--mnemonic",
        type=str,
        default="kitchen subway tomato hire inspire pepper camera frog about kangaroo bunker express length song act oven world quality around elegant lion chimney enough ability prepare",
        help="The 25-word mnemonic of the account to sign transactions.",
    )
    parser.add_argument(
        "--app-id",
        type=str,
        default=1003,
        help="The app id of the submitted smart contract on the network",
    )
    # ADDED: Optional command-line arguments for node URLs
    parser.add_argument(
        "--non-part-1",
        type=str,
        default=None,
        help="URL of the first non-participating node (e.g., 'http://192.168.30.4:4100').",
    )
    parser.add_argument(
        "--non-part-2",
        type=str,
        default=None,
        help="URL of the second non-participating node (e.g., 'http://192.168.30.5:4100').",
    )
    args = parser.parse_args()

    # --- Configuration ---
    mnemonic_1 = args.mnemonic
    private_key = mnemonic.to_private_key(mnemonic_1)
    app_id = args.app_id  # 238906986

    # Initialize counters and data storage
    increment_count = 0
    decrement_count = 0
    x_values, y_values, colors = [], [], []

    # MODIFIED: Client Initialization Logic
    # Define token and headers, mirroring the values in utils.py for custom clients
    algod_token = ""
    algod_headers = {
        "Authorization": "Bearer 97361fdc801fe9fd7f2ae87fa4ea5dc8b9b6ce7380c230eaf5494c4cb5d38d61"
    }

    # Initialize client1: Use custom URL if provided, otherwise use default from utils
    if args.non_part_1:
        print(f"Using custom URL for client 1: {args.non_part_1}")
        client1 = algod.AlgodClient(algod_token, args.non_part_1, algod_headers)
    else:
        print("Using default utility function for client 1.")
        client1 = get_test_non_part_1()

    # Initialize client2: Use custom URL if provided, otherwise use default from utils
    if args.non_part_2:
        print(f"Using custom URL for client 2: {args.non_part_2}")
        client2 = algod.AlgodClient(algod_token, args.non_part_2, algod_headers)
    else:
        print("Using default utility function for client 2.")
        client2 = get_test_non_part_2()


    # Load contract ABI
    script_path = pathlib.Path(__file__).resolve().parent
    contract_json_path = (
        script_path.parent / "last_executed" / "artifacts" / "contract.json"
    )
    with open(contract_json_path) as f:
        contract = abi.Contract.from_json(f.read())

    print("Initial Value: ", print_global_state(client1, app_id), "\n")
    print("Account Address:", account.address_from_private_key(private_key))

    for i in range(50):
        print(f"\n--- Iteration {i + 1}/50 ---")
        print("Previous Value:", print_global_state(client2, app_id))

        # Create two Atomic Transaction Composers
        atc1 = AtomicTransactionComposer()
        atc2 = AtomicTransactionComposer()

        # Add an 'increment' call to the first composer
        atc1.add_method_call(
            app_id=app_id,
            method=contract.get_method_by_name("increment"),
            method_args=[],
            note=str(time.time()).encode(),
            sp=client1.suggested_params(),
            sender=account.address_from_private_key(private_key),
            signer=AccountTransactionSigner(private_key),
        )

        # Add a 'decrement' call to the second composer with a higher fee
        params2 = client2.suggested_params()
        params2.flat_fee = True
        params2.fee = 10000
        atc2.add_method_call(
            app_id=app_id,
            method=contract.get_method_by_name("decrement"),
            method_args=[],
            note=str(time.time()).encode(),
            sp=params2,
            sender=account.address_from_private_key(private_key),
            signer=AccountTransactionSigner(private_key),
        )

        # Submit transactions concurrently
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future2 = executor.submit(submit_atc, atc2, client2)
            future1 = executor.submit(submit_atc, atc1, client1)

            txids1 = future1.result()
            txids2 = future2.result()

            print("TXIDs for 'increment' call: ", txids1)
            print("TXIDs for 'decrement' call: ", txids2)

            # Wait for both transactions to be confirmed
            wait_for_confirmation(client1, txids1[0])
            wait_for_confirmation(client2, txids2[0])

        # Check the result and update counters
        updated_value = print_global_state(client1, app_id)
        print("After Value: ", updated_value)

        if updated_value == "increment":
            print("Result: 'decrement' was executed first.")
            decrement_count += 1
            y_values.append(1)  # 1 for Decrement
            colors.append(1)  # 1 for Red
        elif updated_value == "decrement":
            print("Result: 'increment' was executed first.")
            increment_count += 1
            y_values.append(0)  # 0 for Increment
            colors.append(0)  # 0 for Blue

        x_values.append(i)

    # --- Data Export ---
    total_operations = increment_count + decrement_count
    percentage_increment = (
        (increment_count / total_operations) * 100 if total_operations > 0 else 0
    )
    percentage_decrement = (
        (decrement_count / total_operations) * 100 if total_operations > 0 else 0
    )

    print("\n--- Experiment Complete ---")
    print(f"Increment First: {increment_count} times ({percentage_increment:.2f}%)")
    print(f"Decrement First: {decrement_count} times ({percentage_decrement:.2f}%)")

    # Write results to a CSV file
    with open("experiment_data.csv", "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["Iteration", "FirstFunction", "Color"])
        for i in range(len(x_values)):
            writer.writerow([x_values[i], y_values[i], colors[i]])
    print("\nResults saved to experiment_data.csv")


def submit_atc(atc, client):
    """Submits an AtomicTransactionComposer and returns the transaction IDs."""
    return atc.submit(client)


def print_global_state(client, app_id):
    """Reads and returns the 'counter' value from an application's global state."""
    try:
        response = client.application_info(app_id)
        for item in response["params"]["global-state"]:
            key = base64.b64decode(item["key"]).decode("utf-8")
            if key == "counter":
                return base64.b64decode(item["value"]["bytes"]).decode("utf-8")
    except Exception as e:
        print(f"Could not fetch global state: {e}")
        return None
    return None


def wait_for_confirmation(algod_client, txid, timeout=4):
    """Waits for a transaction to be confirmed."""
    last_round = algod_client.status().get("last-round")
    max_round = last_round + timeout
    while last_round < max_round:
        try:
            pending_txn = algod_client.pending_transaction_info(txid)
        except Exception:
            time.sleep(1)
            last_round += 1
            continue

        if pending_txn.get("confirmed-round", 0) > 0:
            # print(f"Transaction {txid} confirmed in round {pending_txn['confirmed-round']}.")
            return pending_txn
        elif pending_txn.get("pool-error"):
            raise Exception(f'Transaction {txid} has a pool error: {pending_txn["pool-error"]}')

        # print(f"Waiting for confirmation... Current round is {last_round}")
        algod_client.status_after_block(last_round)
        last_round += 1

    raise Exception(f"Transaction {txid} not confirmed after {timeout} rounds.")


if __name__ == "__main__":
    generate_data()
