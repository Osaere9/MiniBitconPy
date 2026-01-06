"""
MiniBitcoinPy CLI.

Command-line interface for interacting with the blockchain.

Commands:
- create-wallet: Generate a new wallet
- balance: Check address balance
- send: Create and send a transaction
- mine: Mine a new block
- peers: Manage peers
- node: Start a node
"""

import json
import sys
from typing import Optional

import httpx
import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from mini_bitcoin_py.core.keys import Wallet, PrivateKey
from mini_bitcoin_py.core.tx import Transaction, TxIn, TxOut

app = typer.Typer(
    name="mini-bitcoin-py",
    help="MiniBitcoinPy - A minimal Bitcoin-like blockchain CLI",
    add_completion=False,
)
console = Console()

# Default node URL
DEFAULT_NODE = "http://localhost:8000"


def make_request(
    method: str,
    url: str,
    json_data: Optional[dict] = None,
    timeout: float = 30.0,
) -> dict:
    """Make HTTP request to node."""
    try:
        with httpx.Client(timeout=timeout) as client:
            if method.upper() == "GET":
                response = client.get(url)
            else:
                response = client.post(url, json=json_data)

            if response.status_code >= 400:
                error = response.json().get("detail", response.text)
                raise typer.Exit(code=1)

            return response.json()
    except httpx.RequestError as e:
        rprint(f"[red]Error connecting to node: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def create_wallet():
    """
    Generate a new wallet (private key, public key, address).

    Example:
        mini-bitcoin-py create-wallet
    """
    wallet = Wallet.generate()
    info = wallet.to_dict()

    rprint("\n[bold green]New Wallet Created[/bold green]\n")

    table = Table(show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Private Key", info["private_key"])
    table.add_row("Public Key", info["public_key"])
    table.add_row("Address", info["address"])

    console.print(table)

    rprint("\n[yellow]IMPORTANT: Save your private key securely! It cannot be recovered.[/yellow]\n")


@app.command()
def balance(
    address: str = typer.Argument(..., help="Address to check balance for"),
    node: str = typer.Option(DEFAULT_NODE, "--node", "-n", help="Node URL"),
):
    """
    Check balance for an address.

    Example:
        mini-bitcoin-py balance <address> --node http://localhost:8000
    """
    url = f"{node.rstrip('/')}/balance/{address}"

    try:
        response = make_request("GET", url)
    except SystemExit:
        rprint(f"[red]Failed to get balance[/red]")
        raise

    rprint(f"\n[bold]Balance for {address}[/bold]")
    rprint(f"  Amount: [green]{response['balance']:,}[/green] satoshis")
    rprint(f"  UTXOs:  {response['utxo_count']}\n")


@app.command()
def utxos(
    address: str = typer.Argument(..., help="Address to get UTXOs for"),
    node: str = typer.Option(DEFAULT_NODE, "--node", "-n", help="Node URL"),
):
    """
    List UTXOs for an address.

    Example:
        mini-bitcoin-py utxos <address>
    """
    url = f"{node.rstrip('/')}/utxos/{address}"

    try:
        response = make_request("GET", url)
    except SystemExit:
        rprint(f"[red]Failed to get UTXOs[/red]")
        raise

    utxos_list = response.get("utxos", [])

    if not utxos_list:
        rprint(f"\n[yellow]No UTXOs found for {address}[/yellow]\n")
        return

    rprint(f"\n[bold]UTXOs for {address}[/bold]\n")

    table = Table(show_header=True)
    table.add_column("TXID", style="cyan")
    table.add_column("Vout", justify="right")
    table.add_column("Amount", justify="right", style="green")

    for utxo in utxos_list:
        table.add_row(
            utxo["txid"][:16] + "...",
            str(utxo["vout"]),
            f"{utxo['amount']:,}",
        )

    console.print(table)
    rprint("")


@app.command()
def send(
    from_privkey: str = typer.Option(..., "--from", "-f", help="Sender's private key (hex)"),
    to_address: str = typer.Option(..., "--to", "-t", help="Recipient's address"),
    amount: int = typer.Option(..., "--amount", "-a", help="Amount to send (satoshis)"),
    node: str = typer.Option(DEFAULT_NODE, "--node", "-n", help="Node URL"),
    fee: int = typer.Option(1000, "--fee", help="Transaction fee (satoshis)"),
):
    """
    Create and send a transaction.

    Example:
        mini-bitcoin-py send --from <privkey> --to <address> --amount 1000000
    """
    # Load wallet
    try:
        wallet = Wallet.from_private_key_hex(from_privkey)
    except Exception as e:
        rprint(f"[red]Invalid private key: {e}[/red]")
        raise typer.Exit(code=1)

    sender_address = wallet.address
    rprint(f"\n[bold]Sending from: {sender_address}[/bold]")

    # Get UTXOs
    utxos_url = f"{node.rstrip('/')}/utxos/{sender_address}"
    try:
        utxos_response = make_request("GET", utxos_url)
    except SystemExit:
        rprint(f"[red]Failed to get UTXOs[/red]")
        raise

    utxos_list = utxos_response.get("utxos", [])
    if not utxos_list:
        rprint(f"[red]No UTXOs available for {sender_address}[/red]")
        raise typer.Exit(code=1)

    # Select UTXOs to cover amount + fee
    total_needed = amount + fee
    selected_utxos = []
    selected_total = 0

    # Sort by amount descending
    sorted_utxos = sorted(utxos_list, key=lambda x: x["amount"], reverse=True)

    for utxo in sorted_utxos:
        selected_utxos.append(utxo)
        selected_total += utxo["amount"]
        if selected_total >= total_needed:
            break

    if selected_total < total_needed:
        rprint(f"[red]Insufficient funds: have {selected_total}, need {total_needed}[/red]")
        raise typer.Exit(code=1)

    # Build transaction
    inputs = []
    for utxo in selected_utxos:
        inputs.append(
            TxIn(
                prev_txid=utxo["txid"],
                prev_index=utxo["vout"],
                signature="",  # Will be filled after signing
                pubkey="",
            )
        )

    outputs = [TxOut(amount=amount, pubkey_hash=to_address)]

    # Add change output if needed
    change = selected_total - total_needed
    if change > 0:
        outputs.append(TxOut(amount=change, pubkey_hash=sender_address))

    tx = Transaction(version=1, inputs=inputs, outputs=outputs, locktime=0)

    # Sign each input
    pubkey_hex = wallet.public_key.to_hex()
    for idx, inp in enumerate(tx.inputs):
        sighash = tx.compute_sighash(idx, sender_address)
        signature = wallet.sign(sighash)
        inp.signature = signature.hex()
        inp.pubkey = pubkey_hex

    # Invalidate txid cache after modifying inputs
    tx.invalidate_txid_cache()

    rprint(f"  Transaction ID: {tx.txid}")
    rprint(f"  Inputs: {len(inputs)}, Outputs: {len(outputs)}")
    rprint(f"  Amount: {amount:,}, Fee: {fee:,}, Change: {change:,}")

    # Submit transaction
    tx_url = f"{node.rstrip('/')}/tx"
    tx_data = {
        "version": tx.version,
        "inputs": [
            {
                "prev_txid": inp.prev_txid,
                "prev_index": inp.prev_index,
                "signature": inp.signature,
                "pubkey": inp.pubkey,
            }
            for inp in tx.inputs
        ],
        "outputs": [
            {"amount": out.amount, "pubkey_hash": out.pubkey_hash}
            for out in tx.outputs
        ],
        "locktime": tx.locktime,
    }

    try:
        response = make_request("POST", tx_url, json_data=tx_data)
        rprint(f"\n[green]Transaction submitted successfully![/green]")
        rprint(f"  TXID: {response.get('txid', tx.txid)}")
        rprint(f"  Fee: {response.get('fee', fee)}\n")
    except SystemExit:
        rprint(f"[red]Failed to submit transaction[/red]")
        raise


@app.command()
def mine(
    miner_address: str = typer.Option(..., "--address", "-a", help="Address to receive mining reward"),
    node: str = typer.Option(DEFAULT_NODE, "--node", "-n", help="Node URL"),
):
    """
    Mine a new block.

    Example:
        mini-bitcoin-py mine --address <your_address>
    """
    rprint(f"\n[bold]Mining block to {miner_address}...[/bold]")

    mine_url = f"{node.rstrip('/')}/mine"

    try:
        response = make_request("POST", mine_url, json_data={"miner_address": miner_address}, timeout=300.0)
    except SystemExit:
        rprint(f"[red]Mining failed[/red]")
        raise

    rprint(f"\n[green]Block mined successfully![/green]")
    rprint(f"  Block Hash: {response.get('block_hash', 'unknown')}")
    rprint(f"  Height: {response.get('height', 'unknown')}")
    rprint(f"  Nonce: {response.get('nonce', 'unknown')}")
    rprint(f"  Time: {response.get('elapsed_seconds', 0):.2f}s")
    rprint(f"  Transactions: {response.get('transactions', 0)}\n")


# Peers commands
peers_app = typer.Typer(help="Peer management commands")
app.add_typer(peers_app, name="peers")


@peers_app.command("list")
def peers_list(
    node: str = typer.Option(DEFAULT_NODE, "--node", "-n", help="Node URL"),
):
    """List known peers."""
    url = f"{node.rstrip('/')}/peers"

    try:
        response = make_request("GET", url)
    except SystemExit:
        rprint(f"[red]Failed to get peers[/red]")
        raise

    peers = response.get("peers", [])
    stored = response.get("stored_peers", [])

    rprint(f"\n[bold]Active Peers ({len(peers)})[/bold]")
    for peer in peers:
        rprint(f"  - {peer}")

    if stored:
        rprint(f"\n[bold]Stored Peers[/bold]")
        for p in stored:
            status = "[green]active[/green]" if p.get("is_active") else "[red]inactive[/red]"
            rprint(f"  - {p['url']} ({status}, failures: {p.get('failures', 0)})")

    rprint("")


@peers_app.command("add")
def peers_add(
    peer_url: str = typer.Argument(..., help="Peer URL to add"),
    node: str = typer.Option(DEFAULT_NODE, "--node", "-n", help="Node URL"),
):
    """Add a peer."""
    url = f"{node.rstrip('/')}/peers/add"

    try:
        response = make_request("POST", url, json_data={"url": peer_url})
        rprint(f"\n[green]{response.get('message', 'Peer added')}[/green]\n")
    except SystemExit:
        rprint(f"[red]Failed to add peer[/red]")
        raise


@app.command()
def sync(
    peer_url: str = typer.Argument(..., help="Peer URL to sync from"),
    node: str = typer.Option(DEFAULT_NODE, "--node", "-n", help="Node URL"),
):
    """
    Sync chain from a peer.

    Example:
        mini-bitcoin-py sync http://localhost:8001
    """
    rprint(f"\n[bold]Syncing from {peer_url}...[/bold]")

    sync_url = f"{node.rstrip('/')}/sync"

    try:
        response = make_request("POST", sync_url, json_data={"peer_url": peer_url}, timeout=120.0)
    except SystemExit:
        rprint(f"[red]Sync failed[/red]")
        raise

    if response.get("synced"):
        rprint(f"\n[green]Sync successful![/green]")
        rprint(f"  New height: {response.get('new_height', 'unknown')}")
    else:
        rprint(f"\n[yellow]{response.get('message', 'Sync not needed')}[/yellow]")

    rprint("")


@app.command()
def status(
    node: str = typer.Option(DEFAULT_NODE, "--node", "-n", help="Node URL"),
):
    """
    Get node status.

    Example:
        mini-bitcoin-py status
    """
    url = f"{node.rstrip('/')}/health"

    try:
        response = make_request("GET", url)
    except SystemExit:
        rprint(f"[red]Failed to get status[/red]")
        raise

    rprint(f"\n[bold]Node Status[/bold]\n")

    table = Table(show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Status", f"[green]{response.get('status', 'unknown')}[/green]")
    table.add_row("Node Name", response.get("node_name", "unknown"))
    table.add_row("Chain Height", str(response.get("chain_height", -1)))
    table.add_row("Tip Hash", response.get("tip_hash", "None")[:32] + "..." if response.get("tip_hash") else "None")
    table.add_row("UTXO Count", str(response.get("utxo_count", 0)))
    table.add_row("Mempool Size", str(response.get("mempool_size", 0)))
    table.add_row("Peer Count", str(response.get("peer_count", 0)))

    console.print(table)
    rprint("")


@app.command()
def node(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
):
    """
    Start a blockchain node.

    Example:
        mini-bitcoin-py node --port 8000
    """
    import uvicorn

    rprint(f"\n[bold]Starting node on {host}:{port}...[/bold]\n")

    uvicorn.run(
        "mini_bitcoin_py.node.api:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    app()
