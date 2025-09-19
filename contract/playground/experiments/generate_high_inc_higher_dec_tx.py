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

load_dotenv()


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

    transaction_log = []

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

    for i in range(100):
        print(f"\n--- Iteration {i} ---")
        previous_value = print_global_state(client2, app_id)
        print("Previous Value:", previous_value)
        atc1 = AtomicTransactionComposer()
        atc2 = AtomicTransactionComposer()

        note_inc = f"inc_{time.time()}_{i}".encode()
        params1 = client1.suggested_params()
        params1.flat_fee = True
        params1.fee = algosdk.constants.MIN_TXN_FEE * 5

        atc1.add_method_call(
            app_id=app_id,
            method=contract.get_method_by_name("increment"),
            method_args=[],
            note=note_inc,
            sp=params1,
            sender=account.address_from_private_key(private_key),
            signer=AccountTransactionSigner(private_key),
        )

        note_dec = f"dec_{time.time()}_{i}".encode()
        params2 = client2.suggested_params()
        params2.flat_fee = True
        params2.fee = algosdk.constants.MIN_TXN_FEE * 1000

        atc2.add_method_call(
            app_id=app_id,
            method=contract.get_method_by_name("decrement"),
            method_args=[],
            note=note_dec,
            sp=params2,
            sender=account.address_from_private_key(private_key),
            signer=AccountTransactionSigner(private_key),
        )

        try:
            current_round = client1.status().get("last-round")
        except Exception:
            current_round = "N/A"


        with concurrent.futures.ThreadPoolExecutor() as executor:
            future1 = executor.submit(submit_atc, atc1, client1)
            future2 = executor.submit(submit_atc, atc2, client2)

            success_inc, result_inc = future1.result()
            success_dec, result_dec = future2.result()

        note_inc_str = note_inc.decode('utf-8')
        note_dec_str = note_dec.decode('utf-8')

        if success_inc:
            txid_inc = result_inc[0]
            print(f"Increment submitted successfully: {txid_inc}")
            confirmation_inc = wait_for_confirmation(client1, txid_inc)
            if confirmation_inc:
                round_inc = confirmation_inc.get('confirmed-round', 'N/A')
                transaction_log.append(
                    {'txid': txid_inc, 'note': note_inc_str, 'type': 'increment',
                     'status': 'Confirmed', 'round': round_inc}
                )
            else:
                transaction_log.append(
                    {'txid': txid_inc, 'note': note_inc_str, 'type': 'increment',
                     'status': 'Not Confirmed', 'round': f'Timed out after round {current_round}'}
                )
        else:
            error_message = result_inc
            print(f"Increment submission failed: {error_message}")
            transaction_log.append(
                {'txid': 'N/A', 'note': note_inc_str, 'type': 'increment',
                 'status': f'Submission Failed: {error_message}', 'round': current_round}
            )

        if success_dec:
            txid_dec = result_dec[0]
            print(f"Decrement submitted successfully: {txid_dec}")
            confirmation_dec = wait_for_confirmation(client2, txid_dec)
            if confirmation_dec:
                round_dec = confirmation_dec.get('confirmed-round', 'N/A')
                transaction_log.append(
                    {'txid': txid_dec, 'note': note_dec_str, 'type': 'decrement',
                     'status': 'Confirmed', 'round': round_dec}
                )
            else:
                transaction_log.append(
                    {'txid': txid_dec, 'note': note_dec_str, 'type': 'decrement',
                     'status': 'Not Confirmed', 'round': f'Timed out after round {current_round}'}
                )
        else:
            error_message = result_dec
            print(f"Decrement submission failed: {error_message}")
            transaction_log.append(
                {'txid': 'N/A', 'note': note_dec_str, 'type': 'decrement',
                 'status': f'Submission Failed: {error_message}', 'round': current_round}
            )

        updated_value = print_global_state(client1, app_id)
        print("After Value: ", updated_value)

        if updated_value == "increment":
            print("Decrement won the race.")
            first_function = "Decrement"
            decrement_count += 1
            color = "red"
        elif updated_value == "decrement":
            print("Increment won the race.")
            first_function = "Increment"
            increment_count += 1
            color = "blue"

        x_values.append(i)
        y_values.append(0) if first_function == "Increment" else y_values.append(1)
        colors.append(0) if color == "blue" else colors.append(1)

    total_operations = increment_count + decrement_count if (
                                                                increment_count + decrement_count) > 0 else 1
    percentage_increment = (increment_count / total_operations) * 100
    percentage_decrement = (decrement_count / total_operations) * 100

    with open("experiment_data.csv", "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "Iteration", "Function", "Color", "Increment Count",
                "Increment Percentage", "Decrement Count", "Decrement Percentage",
            ]
        )
        for i in range(len(x_values)):
            writer.writerow(
                [
                    x_values[i], y_values[i], colors[i], increment_count,
                    percentage_increment, decrement_count, percentage_decrement,
                ]
            )

    log_filename = "transaction_log.csv"
    print(f"\nWriting detailed transaction log to {log_filename}...")
    try:
        with open(log_filename, "w", newline="") as file:
            fieldnames = ['txid', 'note', 'type', 'status', 'round']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(transaction_log)
        print(f"Successfully wrote log to {log_filename}")
    except IOError as e:
        print(f"Error writing to {log_filename}: {e}")


def submit_atc(atc, client):
    """
    Submits an AtomicTransactionComposer object.
    Returns:
        tuple: (True, txids) on success, (False, error_message) on failure.
    """
    try:
        result = atc.submit(client)
        return True, result
    except Exception as e:
        return False, str(e)


def print_global_state(client, app_id):
    try:
        response = client.application_info(app_id)
        counter = None
        if "global-state" in response.get("params", {}):
            for item in response["params"]["global-state"]:
                key = base64.b64decode(item["key"]).decode("utf-8")
                if key == "counter":
                    value_info = item.get("value", {})
                    if value_info.get("type") == 1:  # type 1 is bytes
                        counter = base64.b64decode(value_info.get("bytes", "")).decode("utf-8")
                    return counter
        return "Global state not found or key 'counter' missing."
    except Exception as e:
        print(f"Error reading global state for app {app_id}: {e}")
        return "Error"


def wait_for_confirmation(algod_client, txid, timeout=4):
    """
    Waits for a transaction to be confirmed.
    Returns the transaction information dict on success, or None on failure/timeout.
    """
    last_round = algod_client.status().get("last-round")
    current_round = last_round + 1
    max_round = last_round + timeout

    while current_round <= max_round:
        try:
            tx_info = algod_client.pending_transaction_info(txid)
            if tx_info.get("confirmed-round", 0) > 0:
                print(f"Transaction {txid} confirmed in round {tx_info['confirmed-round']}.")
                return tx_info
            if tx_info.get("pool-error"):
                print(f"Transaction {txid} rejected with error: {tx_info['pool-error']}")
                return None
        except Exception:
            pass

        algod_client.status_after_block(current_round)
        current_round += 1

    print(f"Transaction {txid} not confirmed after {timeout} rounds.")
    return None


def print_address(mn):
    pk_account_a = mnemonic.to_private_key(mn)
    address = account.address_from_private_key(pk_account_a)
    print("Creator Account Address :", address)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run Algorand transaction experiment with optional node URLs, App ID, and Mnemonic."
    )
    parser.add_argument(
        "--non-part-1", type=str,
        help="URL for the first non-participating node (e.g., http://10.1.3.1:4100)",
    )
    parser.add_argument(
        "--non-part-2", type=str,
        help="URL for the second non-participating node (e.g., http://10.1.4.1:4100)",
    )
    parser.add_argument(
        "--app-id", type=int, help="The ID of the application to interact with."
    )
    parser.add_argument(
        "--mnemonic", type=str,
        help="The mnemonic phrase of the account to sign transactions.",
    )
    args = parser.parse_args()

    generate_data(
        non_part_1_url=args.non_part_1,
        non_part_2_url=args.non_part_2,
        app_id_arg=args.app_id,
        mnemonic_arg=args.mnemonic,
    )
