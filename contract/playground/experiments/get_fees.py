import csv
from algosdk.v2client import algod
import argparse
import json

# Default number of recent rounds to scan. Can be overridden by a command-line argument.
DEFAULT_ROUNDS_TO_SCAN = 1000


def find_transaction_fees_in_blocks(txids_to_find, client, rounds_to_scan):
    """
    Scans recent blocks on the chain to find transactions and their fees.

    Args:
        txids_to_find (set): A set of transaction IDs to search for.
        client (algod.AlgodClient): The algod client instance.
        rounds_to_scan (int): The number of recent rounds to scan.

    Returns:
        dict: A dictionary mapping found transaction IDs to their fees.
    """
    found_fees = {}
    remaining_txids = txids_to_find.copy()  # Create a copy to modify as we find TXIDs

    try:
        status = client.status()
        last_round = status['last-round']
        start_round = max(1, last_round - rounds_to_scan)
        print(f"Scanning rounds from {start_round} to {last_round}...")

        # Loop backwards from the last confirmed round
        for round_num in range(last_round, start_round - 1, -1):
            if not remaining_txids:
                print("All transactions found. Stopping scan.")
                break

            # Provide a progress update every 50 rounds to avoid spamming the console
            if round_num % 50 == 0:
                print(f"Scanning block {round_num}... ({len(remaining_txids)} TXIDs remaining)")

            try:
                # Get the block information. The `block_info` method returns a dictionary
                # that includes a 'transactions' key if any exist in the block.
                block = client.block_info(round_num)
                print("="*20 + f" BLOCK {round_num} INFO " + "="*20)
                print(json.dumps(block, indent=4))
                print("="*55 + "\n")


                # Transactions are in a list under the 'transactions' key.
                if 'transactions' in block and block['transactions']:
                    for tx_data in block['transactions']:
                        # The transaction 'id' is the key we need to check against.
                        txid = tx_data.get('id')
                        if txid in remaining_txids:
                            fee = tx_data.get('fee', 0)  # Default to 0 if fee is not present
                            print(
                                f"  -> Found TXID {txid} in block {round_num} with fee {fee} microAlgos")
                            found_fees[txid] = fee
                            remaining_txids.remove(txid)  # Remove from set for efficiency

            except Exception as e:
                print(f"Could not process block {round_num}. Error: {e}")

    except Exception as e:
        print(f"An error occurred while communicating with the node: {e}")

    # Report any transactions that were not found after the scan
    if remaining_txids:
        print("\nWarning: Could not find the following transaction IDs:")
        for txid in remaining_txids:
            print(f" - {txid}")

    return found_fees


def process_transactions(input_file, output_file, client, rounds_to_scan):
    """
    Reads a CSV file of transactions, finds their fees by scanning blocks,
    and writes the results to a new CSV file.
    """
    # Read the input file once to get the TXIDs and store the original data
    txids_to_find = set()
    original_data = []
    try:
        with open(input_file, 'r', newline='') as infile:
            reader = csv.reader(infile)
            header = next(reader)
            original_data.append(header)

            # The txid is in the first column (index 0) of transaction_log.csv
            txid_col_index = 0

            for row in reader:
                if row and len(row) > txid_col_index:
                    txids_to_find.add(row[txid_col_index])
                    original_data.append(row)
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
        return
    except StopIteration:
        print(f"Input file '{input_file}' appears to be empty.")
        return

    if not txids_to_find:
        print("No transaction IDs found in the input file.")
        return

    print(f"\nFound {len(txids_to_find)} unique transaction IDs to search for.")

    # Find the fees for all transactions by scanning blocks
    tx_fees = find_transaction_fees_in_blocks(txids_to_find, client, rounds_to_scan)

    # Write the original data plus the new fee information to the output file
    with open(output_file, 'w', newline='') as outfile:
        writer = csv.writer(outfile)

        # Write the header with the new 'fee_microalgos' column
        header = original_data[0]
        writer.writerow(header + ['fee_microalgos'])

        # Write the data rows, appending the found fee to each
        for row in original_data[1:]:
            txid = row[txid_col_index]
            fee = tx_fees.get(txid, "Not Found")  # Get the fee from our populated dictionary
            writer.writerow(row + [fee])


if __name__ == "__main__":
    # Use argparse for flexible configuration from the command line
    parser = argparse.ArgumentParser(
        description="Scan Algorand blocks for transaction fees from a CSV file."
    )
    parser.add_argument(
        '--input',
        default='transaction_log.csv',
        help='Input CSV file containing transaction data. Defaults to "transaction_log.csv".'
    )
    parser.add_argument(
        '--output',
        default='transaction_log_with_fees.csv',
        help='Output CSV file to write results to. Defaults to "transaction_log_with_fees.csv".'
    )
    parser.add_argument(
        '--algod-address',
        default='http://192.168.30.2:4100',
        help='The address of the Algorand node to connect to.'
    )
    parser.add_argument(
        '--algod-token',
        default='97361fdc801fe9fd7f2ae87fa4ea5dc8b9b6ce7380c230eaf5494c4cb5d38d61',
        help='The authentication token for the Algorand node.'
    )
    parser.add_argument(
        '--rounds',
        type=int,
        default=DEFAULT_ROUNDS_TO_SCAN,
        help=f'Number of recent rounds to scan. Defaults to {DEFAULT_ROUNDS_TO_SCAN}.'
    )

    args = parser.parse_args()

    # --- Client Initialization ---
    print("--- Configuration ---")
    print(f"Input file: {args.input}")
    print(f"Output file: {args.output}")
    print(f"Algod Address: {args.algod_address}")
    print(f"Rounds to Scan: {args.rounds}")
    print("---------------------\n")

    print("Connecting to the Algorand node...")
    try:
        algod_client = algod.AlgodClient(args.algod_token, args.algod_address)
        # Check the connection by fetching node status
        algod_client.status()
        print("Successfully connected to the Algorand node.")
    except Exception as e:
        print(
            f"Failed to connect to the Algorand node at {args.algod_address}. Please check the address and token.")
        print(f"Error: {e}")
        exit()  # Exit if we can't connect

    process_transactions(args.input, args.output, algod_client, args.rounds)

    print(f"\nProcessing complete. Output written to {args.output}")
