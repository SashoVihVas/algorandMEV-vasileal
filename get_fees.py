import csv
from algosdk.v2client import algod
import argparse
import json
import base64

DEFAULT_ROUNDS_TO_SCAN = 1000


def find_transaction_fees_in_blocks(notes_to_find, notes_to_txid, client, rounds_to_scan):

    found_fees = {}
    remaining_notes = notes_to_find.copy()

    try:
        status = client.status()
        last_round = status['last-round']
        start_round = max(1, last_round - rounds_to_scan)
        print(f"Scanning rounds from {start_round} to {last_round}...")

        for round_num in range(last_round, start_round - 1, -1):
            if not remaining_notes:
                print("All transactions found. Stopping scan.")
                break

            if round_num % 50 == 0:
                print(f"Scanning block {round_num}... ({len(remaining_notes)} notes remaining)")

            try:
                block_data = client.block_info(round_num)

                if 'block' in block_data and 'txns' in block_data['block'] and block_data['block'][
                    'txns']:
                    for tx_data in block_data['block']['txns']:
                        raw_txn = tx_data.get('txn', {})
                        b64_note = raw_txn.get('note')

                        if b64_note:
                            try:
                                decoded_note = base64.b64decode(b64_note).decode('utf-8')
                                if decoded_note in remaining_notes:
                                    fee = raw_txn.get('fee', 0)
                                    txid = notes_to_txid[decoded_note]

                                    print(
                                        f"  -> Found note '{decoded_note}' (TXID {txid}) in block {round_num} with fee {fee} microAlgos")
                                    found_fees[txid] = fee
                                    remaining_notes.remove(decoded_note)
                            except Exception:
                                continue

            except Exception as e:
                print(f"Could not process block {round_num}. Error: {e}")

    except Exception as e:
        print(f"An error occurred while communicating with the node: {e}")

    if remaining_notes:
        print("\nWarning: Could not find transactions for the following notes:")
        for note in remaining_notes:
            print(f" - {note} (TXID: {notes_to_txid.get(note, 'N/A')})")

    return found_fees


def process_transactions(input_file, output_file, client, rounds_to_scan):
    notes_to_find = set()
    notes_to_txid = {}
    original_data = []
    try:
        with open(input_file, 'r', newline='') as infile:
            reader = csv.reader(infile)
            header = next(reader)
            original_data.append(header)

            txid_col_index = 0
            note_col_index = 1

            for row in reader:
                if row and len(row) > note_col_index:
                    txid = row[txid_col_index]
                    note = row[note_col_index]
                    notes_to_find.add(note)
                    notes_to_txid[note] = txid
                    original_data.append(row)
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
        return
    except StopIteration:
        print(f"Input file '{input_file}' appears to be empty.")
        return

    if not notes_to_find:
        print("No transaction notes found in the input file.")
        return

    print(f"\nFound {len(notes_to_find)} unique transaction notes to search for.")

    tx_fees = find_transaction_fees_in_blocks(notes_to_find, notes_to_txid, client, rounds_to_scan)

    with open(output_file, 'w', newline='') as outfile:
        writer = csv.writer(outfile)

        header = original_data[0]
        writer.writerow(header + ['fee_microalgos'])
        txid_col_index = header.index('txid')

        for row in original_data[1:]:
            txid = row[txid_col_index]
            fee = tx_fees.get(txid, "Not Found")
            writer.writerow(row + [fee])


if __name__ == "__main__":
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
        default='http://10.1.1.1:4100',
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

    print("--- Configuration ---")
    print(f"Input file: {args.input}")
    print(f"Output file: {args.output}")
    print(f"Algod Address: {args.algod_address}")
    print(f"Rounds to Scan: {args.rounds}")
    print("---------------------\n")

    print("Connecting to the Algorand node...")
    try:
        algod_client = algod.AlgodClient(args.algod_token, args.algod_address)
        algod_client.status()
        print("Successfully connected to the Algorand node.")
    except Exception as e:
        print(
            f"Failed to connect to the Algorand node at {args.algod_address}. Please check the address and token.")
        print(f"Error: {e}")
        exit()

    process_transactions(args.input, args.output, algod_client, args.rounds)

    print(f"\nProcessing complete. Output written to {args.output}")
