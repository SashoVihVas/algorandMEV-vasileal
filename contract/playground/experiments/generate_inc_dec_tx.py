import argparse
import pathlib
import sys
import os

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

from beaker.client import ApplicationClient
from algosdk.atomic_transaction_composer import (
    ABIResult,
    AtomicTransactionComposer,
    TransactionSigner,
    TransactionWithSigner,
)
import base64
import os
from playground.experiments.utils import (
    get_test_non_part_1,
    get_test_non_part_2,
    get_testbed_algod_client,
    get_testnet_TUM_algod_client,
    get_testnet_algod_client,
)
from dotenv import load_dotenv
import csv

load_dotenv()  # take environment variables from .env.

def create_algod_client_from_url(url: str) -> algod.AlgodClient:
    """Creates an AlgodClient instance from a given URL."""
    algod_token = ""
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
    default_mnemonic = "kitchen subway tomato hire inspire pepper camera frog about kangaroo bunker express length song act oven world quality around elegant lion chimney enough ability prepare"
    default_app_id = 1002

    mnemonic_1 = mnemonic_arg if mnemonic_arg is not None else default_mnemonic
    app_id = app_id_arg if app_id_arg is not None else default_app_id

    print(f"--- Configuration ---")
    print(f"Using App ID: {app_id}")
    print(f"Using Mnemonic: {'Provided via CLI' if mnemonic_arg else 'Default'}")
    print(f"---------------------\n")

    private_key = mnemonic.to_private_key(mnemonic_1)

    increment_count = 0
    decrement_count = 0

    x_values = []
    y_values = []
    colors = []

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

    print("Initial Value: ", print_global_state(client1, app_id), "\n")
    print(f"Account Address: {account.address_from_private_key(private_key)}\n")

    for i in range(500):
        previous_value = print_global_state(client2, app_id)
        print("Previous Value:", previous_value)
        atc1 = AtomicTransactionComposer()
        atc2 = AtomicTransactionComposer()
        note = str(time.time()).encode()
        atc1.add_method_call(
            app_id=app_id,
            method=contract.get_method_by_name("increment"),
            method_args=[],
            note=note,
            sp=client1.suggested_params(),
            sender=account.address_from_private_key(private_key),
            signer=AccountTransactionSigner(private_key),
        )

        note = str(time.time()).encode()
        params2 = client2.suggested_params()
        params2.flat_fee = True
        params2.fee = 10000
        atc2.add_method_call(
            app_id=app_id,
            method=contract.get_method_by_name("decrement"),
            method_args=[],
            note=note,
            sp=params2,
            sender=account.address_from_private_key(private_key),
            signer=AccountTransactionSigner(private_key),
        )

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future2 = executor.submit(submit_atc, atc2, client2)
            future1 = executor.submit(submit_atc, atc1, client1)

            txids1 = future1.result()
            txids2 = future2.result()

            print("txids for atc1: ", txids1)
            print("txids for atc2: ", txids2)
            wait_for_confirmation(client1, txids1[0])
            wait_for_confirmation(client2, txids2[0])

        updated_value = print_global_state(client1, app_id)
        print("After Value: ", updated_value, "\n")

        if updated_value == "increment":
            print("decrement first")
            first_function = "Decrement"
            decrement_count += 1
            color = "red"
        elif updated_value == "decrement":
            print("increment first")
            first_function = "Increment"
            increment_count += 1
            color = "blue"

        x_values.append(i)
        y_values.append(0) if first_function == "Increment" else y_values.append(1)
        colors.append(0) if color == "blue" else colors.append(1)

    total_operations = increment_count + decrement_count

    percentage_increment = (increment_count / total_operations) * 100
    percentage_decrement = (decrement_count / total_operations) * 100

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
                ]
            )


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


import time


def wait_for_confirmation(algod_client, txid, timeout=2, retry_delay=3):

    last_round = algod_client.status().get("last-round")
    current_round = last_round + 1
    max_round = last_round + timeout

    while current_round <= max_round:
        try:
            transaction_info = algod_client.pending_transaction_info(txid)

            if (
                "confirmed-round" in transaction_info
                and transaction_info["confirmed-round"] > 0
            ):
                return transaction_info
            elif "pool-error" in transaction_info and transaction_info["pool-error"]:
                print(
                    f"Transaction {txid} rejected with error: {transaction_info['pool-error']}"
                )
                return None
        except Exception as e:
            print(
                f"Error checking transaction {txid}: {e}. Retrying in {retry_delay} seconds..."
            )
            time.sleep(retry_delay)

        print(f"Checking for confirmation in round {current_round}...")

        try:
            algod_client.status_after_block(current_round)
            current_round += 1
        except Exception as e:
            print(
                f"Error waiting for block {current_round}: {e}. Retrying in {retry_delay} seconds..."
            )
            time.sleep(retry_delay)

    raise Exception(f"Transaction {txid} not confirmed after {timeout} rounds")


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
