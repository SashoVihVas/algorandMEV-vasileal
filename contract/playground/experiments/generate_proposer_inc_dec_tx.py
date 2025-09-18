import pathlib
import sys
import os
import argparse

# Add the 'contract' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import time
import algosdk
import pyteal as pt
import algokit_utils
import json
from algosdk import mnemonic, account, transaction, atomic_transaction_composer, abi
from algosdk.v2client import algod
from algosdk.atomic_transaction_composer import AccountTransactionSigner
import concurrent.futures
import msgpack
from beaker.client import ApplicationClient
from algosdk.atomic_transaction_composer import (
    ABIResult,
    AtomicTransactionComposer,
    TransactionSigner,
    TransactionWithSigner,
)
from concurrent.futures import ThreadPoolExecutor
import base64
import os
from playground.experiments.utils import (
    get_test_non_part_2,
    get_test_non_part_1,
)
from dotenv import load_dotenv
import csv

load_dotenv()  # take environment variables from .env.

# Initialize lists to track proposers and confirmed rounds
proposers_1 = []
proposers_2 = []
confirmed_rounds_1 = []
confirmed_rounds_2 = []

def create_algod_client_from_url(url: str) -> algod.AlgodClient:
    """Creates an AlgodClient instance from a given URL."""
    algod_token = ""
    # Assuming the same auth token for custom URLs as in your utils
    algod_headers = {
        "Authorization": "Bearer 97361fdc801fe9fd7f2ae87fa4ea5dc8b9b6ce7380c230eaf5494c4cb5d38d61"
    }
    return algod.AlgodClient(algod_token, url, algod_headers)


def generate_data(
    non_part_1_url: str | None = None,
    non_part_2_url: str | None = None,
    app_id_arg: int | None = None,
    mnemonic_arg: str | None = None,
):
    # Define default values
    default_mnemonic = "kitchen subway tomato hire inspire pepper camera frog about kangaroo bunker express length song act oven world quality around elegant lion chimney enough ability prepare"
    default_app_id = 1002

    # Use provided arguments or fall back to defaults
    mnemonic_1 = mnemonic_arg if mnemonic_arg is not None else default_mnemonic
    app_id = app_id_arg if app_id_arg is not None else default_app_id

    print(f"--- Configuration ---")
    print(f"Using App ID: {app_id}")
    print(f"Using Mnemonic: {'Provided via CLI' if mnemonic_arg else 'Default'}")
    print(f"---------------------\n")

    private_key = mnemonic.to_private_key(mnemonic_1)

    # Initialize counters for increment and decrement functions
    increment_count = 0
    decrement_count = 0

    # Initialize lists to store data for scatter plot
    x_values = []  # Function names
    y_values = []  # Frequency of each function
    colors = []  # Color of each point

    first_function = "None"
    color = ""

    if non_part_1_url:
        print(f"Using provided URL for client 1: {non_part_1_url}")
        client1 = create_algod_client_from_url(non_part_1_url)
    else:
        print("Using default utils.py function for client 1.")
        client1 = get_test_non_part_1()

    if non_part_2_url:
        print(f"Using provided URL for client 2: {non_part_2_url}")
        client2 = create_algod_client_from_url(non_part_2_url)
    else:
        print("Using default utils.py function for client 2.")
        client2 = get_test_non_part_2()

    script_path = pathlib.Path(__file__).resolve().parent
    contract_json_path = script_path.parent / "last_executed" / "artifacts" / "contract.json"

    with open(contract_json_path) as f:
        js = f.read()
    contract = abi.Contract.from_json(js)

    for i in range(500):
        previous_value = print_global_state(client2, app_id)
        print("Previous Value:", previous_value)
        atc1 = AtomicTransactionComposer()
        atc2 = AtomicTransactionComposer()
        atc1.add_method_call(
            app_id=app_id,
            method=contract.get_method_by_name("decrement"),
            method_args=[],
            sp=client1.suggested_params(),
            sender=account.address_from_private_key(private_key),
            signer=AccountTransactionSigner(private_key),
        )

        atc2.add_method_call(
            app_id=app_id,
            method=contract.get_method_by_name("increment"),
            method_args=[],
            sp=client2.suggested_params(),
            sender=account.address_from_private_key(private_key),
            signer=AccountTransactionSigner(private_key),
        )

        # Using ThreadPoolExecutor to send transactions in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            result1 = executor.submit(submit_and_wait_for_conf, client1, atc1)
            result2 = executor.submit(submit_and_wait_for_conf, client2, atc2)

            txids1, transaction_info_1, confirmed_round_1, proposer_1 = result1.result()
            txids2, transaction_info_2, confirmed_round_2, proposer_2 = result2.result()

            print("txids for atc1: ", txids1)
            print("txids for atc2: ", txids2)
        #  Execute submit_atc directly for both atc1 and atc2
        # txids2 = submit_atc(atc2, client2)
        # txids1 = submit_atc(atc1, client1)

        # print("txids for atc1: ", txids1)
        # print("txids for atc2: ", txids2)

        # transaction_info_1, confirmed_round_1 = wait_for_confirmation(client1, txids1[0])
        # transaction_info_2, confirmed_round_2 = wait_for_confirmation(client2, txids2[0])

        # proposer_1 = get_block_proposer(client1, confirmed_round_1)
        # # proposer_2 = get_block_proposer(client2, confirmed_round_2)

        proposers_1.append(proposer_1)
        # proposers_2.append(proposer_2)
        confirmed_rounds_1.append(confirmed_round_1)
        # confirmed_rounds_2.append(confirmed_round_2)

        # proposers_1.append(proposer_1)
        # proposers_2.append(proposer_2)
        # confirmed_rounds_1.append(confirmed_round_1)
        # confirmed_rounds_2.append(confirmed_round_2)

        updated_value = print_global_state(client1, app_id)
        print("After Value: ", updated_value, "\n")

        if updated_value == "increment":
            print("decrement first")
            first_function = "Decrement"
            decrement_count += 1
            color = "red"  # Assign red color for Decrement
        elif updated_value == "decrement":
            print("increment first")
            first_function = "Increment"
            increment_count += 1
            color = "blue"

        # Append data to lists for scatter plot
        x_values.append(i)
        y_values.append(0) if first_function == "Increment" else y_values.append(1)
        colors.append(0) if color == "blue" else colors.append(1)
        print("before sleep")
        time.sleep(2)
        print("after sleep")

    # Calculate the total number of operations
    total_operations = increment_count + decrement_count

    # Calculate the percentage of increment and decrement operations
    percentage_increment = (increment_count / total_operations) * 100
    percentage_decrement = (decrement_count / total_operations) * 100

    # After the experiment, write the data to a CSV file
    with open("experiment_data.csv", "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "Iteration",
                "Function",
                "Color",
                "Increment Count",
                "Increment Percentage",
                "Decrement Count",
                "Decrement Percentage",
                "Proposer 1",
                "confirmed_round_1",
                # "Proposer 2",
                # "confirmed_round_2"
            ]
        )
        for i in range(len(x_values)):
            writer.writerow(
                [
                    x_values[i],
                    y_values[i],
                    colors[i],
                    increment_count,
                    percentage_increment,
                    decrement_count,
                    percentage_decrement,
                    proposers_1[i],  # Use data from the list
                    confirmed_rounds_1[i],  # Use data from the list
                    # proposers_2[i],         # Use data from the list
                    # confirmed_rounds_2[i]   # Use data from the list
                ]
            )


def submit_and_wait_for_conf(client, atc):
    txids = submit_atc(atc, client)
    transaction_info, confirmed_round = wait_for_confirmation(client, txids[0])
    proposer = get_block_proposer(client, confirmed_round)
    return txids, transaction_info, confirmed_round, proposer


def get_block_proposer(client, confirmed_round: int):
    try:
        response = client.block_info(confirmed_round, response_format="msgpack")
        decoded_response = msgpack.unpackb(response, raw=True, strict_map_key=False)
        proposer = decoded_response[b"cert"][b"prop"][b"oprop"]
        proposer = algod.encoding.encode_address(proposer)
        return proposer
    except Exception as e:
        print(f"An error at block {confirmed_round} occurred: {e}")
        return None


def submit_atc(atc, client):
    return atc.submit(client)


def print_global_state(client, app_id):
    response = client.application_info(app_id)
    counter = None
    for item in response["params"]["global-state"]:
        key = base64.b64decode(item["key"]).decode("utf-8")
        if key == "counter":
            counter = base64.b64decode(item["value"]["bytes"]).decode("utf-8")
            return counter


def wait_for_confirmation(algod_client, txid, timeout=4):
    """
    Wait for the transaction to be confirmed.

    Args:
        algod_client (algosdk.algod.AlgodClient): Algorand client instance.
        txid (str): Transaction ID.
        timeout (int, optional): Maximum number of rounds to wait for confirmation. Defaults to 4.

    Returns:
        tuple: A tuple containing confirmed transaction information and the confirmed round.
    """
    last_round = algod_client.status().get("last-round")
    current_round = last_round + 1
    while current_round < last_round + timeout:
        try:
            # Check if the transaction is confirmed
            transaction_info = algod_client.pending_transaction_info(txid)
            confirmed_round = transaction_info.get("confirmed-round", 0)
            if confirmed_round > 0:
                return transaction_info, confirmed_round
        except Exception as e:
            print(f"Exception: {str(e)}")
            print(f"Waiting for confirmation... (current round: {current_round})")

        # Wait for the next round
        algod_client.status_after_block(current_round)
        current_round += 1

    raise Exception(f"Transaction not confirmed after {timeout} rounds")


def print_address(mn):
    pk_account_a = mnemonic.to_private_key(mn)
    address = account.address_from_private_key(pk_account_a)
    print("Creator Account Address :", address)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run Algorand transaction experiment with optional node URLs, App ID, and Mnemonic."
    )
    parser.add_argument(
        "--non-part-1",
        type=str,
        help="URL for the first non-participating node (e.g., http://10.1.3.1:4100)",
    )
    parser.add_argument(
        "--non-part-2",
        type=str,
        help="URL for the second non-participating node (e.g., http://10.1.4.1:4100)",
    )
    parser.add_argument(
        "--app-id",
        type=int,
        help="The ID of the application to interact with.",
    )
    parser.add_argument(
        "--mnemonic",
        type=str,
        help="The mnemonic phrase of the account to sign transactions.",
    )
    args = parser.parse_args()

    generate_data(
        non_part_1_url=args.non_part_1,
        non_part_2_url=args.non_part_2,
        app_id_arg=args.app_id,
        mnemonic_arg=args.mnemonic,
    )
