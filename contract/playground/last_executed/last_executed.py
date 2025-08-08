import sys
import os
import pathlib
import base64
import argparse  # Import the argparse library

# Add the 'contract' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pyteal as pt
from algosdk import mnemonic, account, transaction
from algosdk.atomic_transaction_composer import AccountTransactionSigner
from algosdk.v2client import algod
from beaker import Application, Authorize, GlobalStateValue, unconditional_create_approval
from beaker.client import ApplicationClient
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.


class LastExecutedState:
    counter = GlobalStateValue(
        stack_type=pt.TealType.bytes,
        default=pt.Bytes("None"),
        descr="A counter for showing how to use application state",
    )


last_executed = Application("LastExecutedApp", state=LastExecutedState()).apply(
    unconditional_create_approval, initialize_global_state=True
)


@last_executed.external(authorize=Authorize.only_creator())
def increment(*, output: pt.abi.String) -> pt.Expr:
    """increment the counter"""
    return pt.Seq(
        last_executed.state.counter.set(pt.Bytes("increment")),
        output.set(last_executed.state.counter),
    )


@last_executed.external(authorize=Authorize.only_creator())
def decrement(*, output: pt.abi.String) -> pt.Expr:
    """decrement the counter"""
    return pt.Seq(
        last_executed.state.counter.set(pt.Bytes("decrement")),
        output.set(last_executed.state.counter),
    )


def demo() -> None:
    # --- Argument Parsing ---
    # Set up the argument parser to handle command-line inputs
    parser = argparse.ArgumentParser(description="Deploy and interact with a Beaker application.")

    # Add argument for the node's address with a default value
    parser.add_argument(
        '--node-address',
        type=str,
        default="http://10.1.1.1:4100",
        help="The address of the Algorand node."
    )

    # Add argument for the account mnemonic with a default value
    parser.add_argument(
        '--mnemonic',
        type=str,
        default="kitchen subway tomato hire inspire pepper camera frog about kangaroo bunker express length song act oven world quality around elegant lion chimney enough ability prepare",
        help="The mnemonic of the account to use. For demonstration purposes only."
    )

    # Parse the arguments provided at runtime
    args = parser.parse_args()

    # --- Configuration ---
    # Use the parsed arguments or their default values
    algod_address = args.node_address
    account_mnemonic = args.mnemonic

    # Define the API token directly
    token = "97361fdc801fe9fd7f2ae87fa4ea5dc8b9b6ce7380c230eaf5494c4cb5d38d61"

    # --- Client and Account Setup ---
    # Initialize the client correctly: (token, address). No custom headers needed.
    client = algod.AlgodClient(token, algod_address)
    private_key = mnemonic.to_private_key(account_mnemonic)
    signer = AccountTransactionSigner(private_key)
    sender_address = account.address_from_private_key(private_key)
    print(f"Using Account Address: {sender_address}")

    # --- Application Deployment and Interaction ---
    try:
        # Create an Application client
        app_client = ApplicationClient(
            client=client,
            app=last_executed,
            signer=signer,
        )

        print("Creating and deploying the application...")
        # Create and deploy the application on-chain
        app_id, app_addr, txid = app_client.create()
        print(
            f"Successfully Created App!\n"
            f"--> App ID: {app_id}\n"
            f"--> App Address: {app_addr}\n"
            f"--> Transaction ID: {txid}"
        )

        print("\nCalling 'increment' method...")
        app_client.call(increment)

        print("Calling 'decrement' method...")
        app_client.call(decrement)

        app_state = app_client.get_global_state()
        print(f"\nCurrent Application State: {app_state}")

    except Exception as e:
        print(f"\nAn error occurred: {e}")


if __name__ == "__main__":
    demo()
