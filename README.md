# MiniBitcoinPy 🪙

> A minimal Bitcoin-like Proof-of-Work blockchain node in Python. Learn how blockchains work by running your own network.

**MiniBitcoinPy** is a fully functional, educational blockchain implementation featuring UTXO transactions, ECDSA signatures, Proof-of-Work mining, and peer-to-peer networking. Built with Python 3.11+, FastAPI, and PostgreSQL, it demonstrates core Bitcoin concepts in a clean, readable codebase.

---

## 🎯 Project Status

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-beta-yellow.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)

**Status**: Beta — Core features complete, suitable for learning and experimentation.

---

## ✨ Key Features

- **UTXO Model**: Unspent Transaction Output system matching Bitcoin's design
- **ECDSA Signatures**: secp256k1 signing with compressed public keys (via `coincurve`)
- **Proof-of-Work**: Configurable difficulty mining with target adjustment
- **Merkle Trees**: Transaction integrity verification via Merkle roots
- **P2P Networking**: HTTP-based peer communication with transaction/block broadcasting
- **Chain Synchronization**: Automatic chain sync and reorg handling
- **PostgreSQL Persistence**: Full blockchain state stored in SQL with Alembic migrations
- **REST API**: FastAPI-based node API for queries and operations
- **CLI Tool**: Rich terminal interface for wallet management, mining, and transactions
- **Multi-Node Support**: Docker Compose setup for running 3+ nodes locally

---

## 🚀 Quick Demo Preview

**What you'll do in 10 minutes:**

1. **Start the network**: Launch 3 nodes + PostgreSQL with Docker Compose
2. **Create wallets**: Generate keypairs and addresses for Alice and Bob
3. **Mine genesis**: Mine the first block to fund Alice's wallet
4. **Send transaction**: Alice sends coins to Bob with a signed transaction
5. **Mine block**: Mine a block containing the transaction
6. **Verify**: Check balances and confirm the transaction is in the chain

---

## 🏃 Quickstart

### Prerequisites

- **Docker & Docker Compose** (for multi-node setup)
- **Python 3.11+** (if running without Docker)
- **PostgreSQL 15+** (if running without Docker)

### Option 1: Docker Compose (Recommended)

Clone and start the network:

```bash
git clone https://github.com/your-username/mini-bitcoin-py.git
cd mini-bitcoin-py
docker-compose -f docker/docker-compose.yml up -d
```

This starts:
- **PostgreSQL** on port `5432`
- **Node 1** on port `8001` (http://localhost:8001)
- **Node 2** on port `8002` (http://localhost:8002)
- **Node 3** on port `8003` (http://localhost:8003)

Wait ~10 seconds for nodes to initialize, then check status:

```bash
curl http://localhost:8001/health
```

### Option 2: Local Development

1. **Install dependencies**:

```bash
pip install -e ".[dev]"
```

2. **Set up PostgreSQL**:

```bash
# Create database
createdb minibitcoinpy

# Or use the init script
psql -U postgres -f docker/init-db.sql
```

3. **Configure environment** (create `.env`):

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/minibitcoinpy
NODE_HOST=0.0.0.0
NODE_PORT=8000
NODE_NAME=node1
LOG_LEVEL=INFO
DEFAULT_TARGET=0x00000fffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
BLOCK_REWARD=5000000000
```

4. **Run migrations**:

```bash
alembic upgrade head
```

5. **Start a node**:

```bash
mini-bitcoin-py node --port 8000
```

---

## 📖 Usage

### CLI Commands

The CLI provides a rich interface for interacting with nodes:

#### Create a Wallet

```bash
mini-bitcoin-py create-wallet
```

**Output:**
```
New Wallet Created

Field         Value
────────────────────────────────────────────────────────────
Private Key   a1b2c3d4e5f6... (64 hex chars)
Public Key    02a1b2c3d4e5... (66 hex chars, compressed)
Address       f9e8d7c6b5a4... (40 hex chars, HASH160)
```

> **⚠️ Security Note**: Save your private key securely! It cannot be recovered.

#### Check Balance

```bash
mini-bitcoin-py balance f9e8d7c6b5a43210987654321098765432109876 --node http://localhost:8001
```

#### List UTXOs

```bash
mini-bitcoin-py utxos f9e8d7c6b5a43210987654321098765432109876
```

#### Mine a Block

```bash
mini-bitcoin-py mine --address f9e8d7c6b5a43210987654321098765432109876 --node http://localhost:8001
```

**Output:**
```
Block mined successfully!
  Block Hash: 3a4b5c6d7e8f...
  Height: 1
  Nonce: 1234567
  Time: 2.34s
  Transactions: 1
```

#### Send a Transaction

```bash
mini-bitcoin-py send \
  --from a1b2c3d4e5f6... \
  --to f9e8d7c6b5a43210987654321098765432109876 \
  --amount 1000000 \
  --fee 1000 \
  --node http://localhost:8001
```

The CLI automatically:
1. Fetches your UTXOs
2. Selects inputs to cover amount + fee
3. Creates change output if needed
4. Signs all inputs
5. Submits to mempool

#### View Node Status

```bash
mini-bitcoin-py status --node http://localhost:8001
```

### REST API Examples

#### Get Chain Info

```bash
curl http://localhost:8001/chain
```

#### Get Specific Block

```bash
curl http://localhost:8001/block/3a4b5c6d7e8f9012345678901234567890123456789012345678901234567890ab
```

#### Get Mempool

```bash
curl http://localhost:8001/mempool
```

#### Submit Transaction (JSON)

```bash
curl -X POST http://localhost:8001/tx \
  -H "Content-Type: application/json" \
  -d '{
    "version": 1,
    "inputs": [{
      "prev_txid": "ab12cd34...",
      "prev_index": 0,
      "signature": "3045022100...",
      "pubkey": "02a1b2c3..."
    }],
    "outputs": [{
      "amount": 1000000,
      "pubkey_hash": "f9e8d7c6..."
    }],
    "locktime": 0
  }'
```

---

## 🌐 Multi-Node Networking

### Adding Peers

Nodes discover each other via the `/peers` endpoint. To connect node2 to node1:

```bash
# On node2
curl -X POST http://localhost:8002/peers/add \
  -H "Content-Type: application/json" \
  -d '{"url": "http://node1:8000"}'

# Or via CLI
mini-bitcoin-py peers add http://localhost:8001 --node http://localhost:8002
```

### Transaction Propagation

1. **Submit transaction** to node1:
   ```bash
   mini-bitcoin-py send --from <key> --to <address> --amount 1000 --node http://localhost:8001
   ```

2. **Node1 validates** and adds to mempool

3. **Node1 broadcasts** to all connected peers (node2, node3)

4. **Other nodes validate** and add to their mempools

5. **When mined**, the transaction is included in a block and broadcast

### Block Propagation

When a node mines a block:

1. **Miner validates** the block (PoW, transactions, merkle root)

2. **Miner adds** block to local chain and updates UTXO set

3. **Miner broadcasts** block to all peers via `/block` endpoint

4. **Peers validate** and add to their chains (if valid and extends their tip)

5. **Peers update** their UTXO sets and remove mined transactions from mempool

### Chain Synchronization

Sync node2 from node1:

```bash
mini-bitcoin-py sync http://localhost:8001 --node http://localhost:8002
```

Or via API:

```bash
curl -X POST http://localhost:8002/sync \
  -H "Content-Type: application/json" \
  -d '{"peer_url": "http://localhost:8001"}'
```

**What happens:**
1. Node2 requests full chain from node1 (`/chain` endpoint)
2. Node2 validates all blocks
3. If node1's chain has more work, node2 adopts it (reorg if needed)
4. Node2 rebuilds UTXO set from the new chain

---

## 🏗️ Architecture

```mermaid
graph TB
    subgraph "CLI Layer"
        CLI[CLI Tool<br/>mini-bitcoin-py]
    end
    
    subgraph "Node Layer"
        API[FastAPI REST API]
        P2P[P2P Manager<br/>HTTP Networking]
        SYNC[Chain Synchronizer]
        MEMPOOL[Mempool Manager]
    end
    
    subgraph "Core Layer"
        BLOCK[Block/BlockHeader]
        TX[Transaction/TxIn/TxOut]
        UTXO[UTXO Set]
        CONSENSUS[PoW Mining]
        VALIDATION[Validation Rules]
        KEYS[ECDSA Keys/Wallet]
        MERKLE[Merkle Tree]
    end
    
    subgraph "Storage Layer"
        DB[(PostgreSQL)]
        BLOCK_STORE[Block Storage]
        STATE_STORE[Chain State]
        PEER_STORE[Peer Storage]
    end
    
    CLI --> API
    API --> P2P
    API --> SYNC
    API --> MEMPOOL
    API --> BLOCK_STORE
    API --> STATE_STORE
    
    SYNC --> BLOCK
    SYNC --> VALIDATION
    SYNC --> UTXO
    
    MEMPOOL --> TX
    MEMPOOL --> VALIDATION
    MEMPOOL --> UTXO
    
    BLOCK --> MERKLE
    BLOCK --> CONSENSUS
    TX --> KEYS
    TX --> VALIDATION
    
    BLOCK_STORE --> DB
    STATE_STORE --> DB
    PEER_STORE --> DB
    
    P2P -.->|HTTP| P2P
```

### Module Structure

```
mini_bitcoin_py/
├── core/              # Core blockchain logic
│   ├── block.py       # Block and BlockHeader
│   ├── tx.py          # Transaction, TxIn, TxOut
│   ├── utxo.py        # UTXO set management
│   ├── consensus.py    # PoW mining and work calculation
│   ├── validation.py  # Transaction and block validation
│   ├── keys.py        # ECDSA key management
│   ├── hashing.py     # SHA256, double SHA256, HASH160
│   ├── merkle.py      # Merkle tree computation
│   └── encoding.py    # Deterministic serialization
│
├── node/              # Node infrastructure
│   ├── api.py         # FastAPI REST endpoints
│   ├── p2p.py         # P2P networking (HTTP)
│   ├── sync.py        # Chain synchronization
│   ├── storage.py     # Database operations
│   ├── models.py      # SQLAlchemy models
│   ├── db.py          # Database connection
│   └── config.py      # Configuration management
│
└── cli/               # Command-line interface
    └── main.py        # Typer-based CLI

tests/                  # Comprehensive test suite
docker/                 # Docker Compose setup
```

---

## 💾 Data Model & Storage

### PostgreSQL Tables

**`blocks`**
- Stores all blocks with denormalized header fields
- Full block data in JSONB column
- Indexed by `block_hash`, `height`, `prev_hash`

**`chain_state`**
- Singleton row tracking current tip
- Fields: `tip_hash`, `tip_height`, `current_target`, `cumulative_work`

**`peers`**
- Known peer URLs with status tracking
- Fields: `url`, `is_active`, `last_seen`, `failures`

**`mempool_txs`** (optional)
- Persisted mempool transactions
- Fields: `txid`, `tx_data` (JSONB), `fee`, `received_at`

### UTXO Set

The UTXO set is **rebuilt on startup** from stored blocks. This ensures consistency but means startup time scales with chain length. For production, consider maintaining a persistent UTXO index.

### Migrations

Alembic manages database schema:

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## ⚖️ Consensus & Validation Rules

### Proof-of-Work

- **Target**: 256-bit integer (stored as hex string)
- **Validity**: `int(block_hash, 16) <= target`
- **Work Calculation**: `work = 2^256 / (target + 1)`
- **Best Chain**: Highest cumulative work
- **Target Adjustment**: Every 10 blocks, adjusts based on actual vs expected time (max 4x per interval)

### Block Validation

A block is valid if:

1. ✅ **Previous block exists** (or genesis with `prev_hash = 00...00`)
2. ✅ **Timestamp not too far in future** (max 2 hours drift)
3. ✅ **Merkle root matches** computed value from transactions
4. ✅ **PoW is valid** (`block_hash <= target`)
5. ✅ **Exactly one coinbase** transaction (first transaction)
6. ✅ **All transactions valid** (see transaction rules below)
7. ✅ **Coinbase output** ≤ `block_reward + total_fees`
8. ✅ **No double-spends** within the block

### Transaction Validation

A transaction is valid if:

1. ✅ **Has inputs and outputs** (non-empty)
2. ✅ **Output amounts** ≥ 0
3. ✅ **No duplicate inputs**
4. ✅ **All inputs reference existing UTXOs**
5. ✅ **No double-spend** (UTXO not already spent)
6. ✅ **Input sum** ≥ output sum (difference is fee)
7. ✅ **Valid signatures**: For each input:
   - Signature verifies against `pubkey`
   - `HASH160(pubkey) == UTXO.pubkey_hash`
8. ✅ **Coinbase transactions** only allowed in blocks (not mempool)

### UTXO Rules

- Each UTXO can only be spent **once**
- Spending requires a **valid signature** from the key that hashes to the UTXO's `pubkey_hash`
- UTXOs are **removed** when spent, **created** when a transaction is confirmed

---

## 🔐 Deterministic Serialization & Signing

### Why Deterministic?

All hashing (block hashes, transaction IDs, Merkle roots) uses **deterministic byte encoding**, not JSON or dict representations. This ensures:
- Same data → same hash (critical for consensus)
- Cross-language compatibility
- Predictable signing

### Serialization Format

**Block Header** (108 bytes):
```
version (4 bytes, little-endian int32)
prev_hash (32 bytes)
merkle_root (32 bytes)
timestamp (4 bytes, little-endian uint32)
target (32 bytes, big-endian)
nonce (4 bytes, little-endian uint32)
```

**Transaction** (for txid):
```
version (4 bytes)
varint(input_count) + inputs (prev_txid + prev_index only)
varint(output_count) + outputs (amount + pubkey_hash)
locktime (4 bytes)
```

> **Note**: Signatures are **excluded** from txid to avoid circular dependency.

### Sighash (Simplified)

For each input being signed:

1. Create preimage:
   - `version` (4 bytes)
   - All inputs: `prev_txid + prev_index + (pubkey_hash if signing this input, else empty)`
   - All outputs: `amount + pubkey_hash`
   - `locktime` (4 bytes)

2. Hash: `sighash = double_sha256(preimage)`

3. Sign: `signature = ECDSA_sign(sighash, private_key)`

> **Simplification**: Real Bitcoin uses `SIGHASH_ALL` by default, but supports other flags. This implementation uses a simplified scheme.

---

## ⚙️ Configuration

### Environment Variables

```env
# Database
DATABASE_URL=postgresql://user:pass@host:port/dbname

# Node
NODE_HOST=0.0.0.0
NODE_PORT=8000
NODE_NAME=node1

# Mining
DEFAULT_TARGET=0x00000fffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
BLOCK_REWARD=5000000000  # 50 "coins" (8 decimal places)
MAX_BLOCK_TXS=100

# P2P
BOOTSTRAP_PEERS=http://node1:8000,http://node2:8000
MAX_PEERS=50
SYNC_INTERVAL=30

# Logging
LOG_LEVEL=INFO
```

### Target Difficulty

The `DEFAULT_TARGET` controls mining difficulty. Lower target = harder mining.

**Examples:**
- `0x00000fff...` (20 leading zero bits) - Very easy, ~1 second
- `0x0000000f...` (28 leading zero bits) - Medium, ~10 seconds
- `0x00000000...` (32+ leading zero bits) - Hard, minutes+

Adjust based on your hardware and desired block time.

---

## 🧪 Testing, Linting, Formatting

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=mini_bitcoin_py --cov-report=html

# Specific test file
pytest tests/test_utxo_rules.py -v
```

### Linting

```bash
# Ruff (fast Python linter)
ruff check .

# Auto-fix
ruff check --fix .
```

### Formatting

```bash
# Black (code formatter)
black .

# isort (import sorting, via ruff)
ruff check --select I --fix .
```

### Type Checking

```bash
mypy mini_bitcoin_py
```

---

## 🔒 Security, Limitations & Non-Goals

### Security Considerations

- ✅ **ECDSA signatures** use secp256k1 (same as Bitcoin)
- ✅ **Deterministic serialization** prevents hash collisions
- ✅ **UTXO validation** prevents double-spends
- ⚠️ **No encryption** of network traffic (HTTP, not HTTPS)
- ⚠️ **No rate limiting** on API endpoints
- ⚠️ **Private keys** stored in plaintext (use secure storage in production)

### Simplifications vs. Real Bitcoin

| Feature | Bitcoin | MiniBitcoinPy |
|---------|---------|---------------|
| **P2P Protocol** | TCP with custom protocol | HTTP REST API |
| **Scripting** | Full Script language | Simplified (pubkey_hash only) |
| **Reorg Handling** | Complex, handles deep reorgs | Simplified (full chain rebuild) |
| **Mempool** | Sophisticated fee estimation | Simple FIFO with fee priority |
| **Block Size** | 1MB limit + SegWit | Configurable, no hard limit |
| **Difficulty Adjustment** | Every 2016 blocks, precise | Every 10 blocks, simplified |
| **Network Discovery** | DNS seeds, hardcoded nodes | Manual peer addition |
| **SPV Support** | Merkle proofs for light clients | Not implemented |

### Non-Goals

This project is **not intended for**:
- Production cryptocurrency use
- Real-world value transfer
- Competing with Bitcoin
- High-performance mining

It **is intended for**:
- Learning blockchain concepts
- Experimentation and research
- Educational demonstrations
- Code portfolio projects

---

## 🐛 Troubleshooting / FAQ

### Database Connection Issues

**Error**: `could not connect to server`

**Solutions**:
- Check PostgreSQL is running: `pg_isready`
- Verify `DATABASE_URL` in `.env`
- Check firewall/port 5432 is open
- For Docker: ensure postgres container is healthy

### Port Conflicts

**Error**: `Address already in use`

**Solutions**:
- Change `NODE_PORT` in `.env`
- Or use `--port` flag: `mini-bitcoin-py node --port 8001`
- Check what's using the port: `netstat -ano | findstr :8000` (Windows) or `lsof -i :8000` (Linux/Mac)

### Nodes Not Syncing

**Symptoms**: Nodes show different chain heights

**Solutions**:
1. Check peers are connected: `curl http://localhost:8001/peers`
2. Manually trigger sync: `mini-bitcoin-py sync http://localhost:8001 --node http://localhost:8002`
3. Check logs for validation errors
4. Ensure nodes can reach each other (check Docker network)

### Why is Mining Slow/Fast?

**Mining speed depends on**:
- **Target difficulty**: Lower target = slower
- **CPU performance**: Single-threaded by default
- **Block time**: Adjust target to achieve ~10s blocks

**To make mining faster**:
- Increase target (more leading F's in hex)
- Use a faster CPU
- Reduce target adjustment interval

**To make mining slower** (more realistic):
- Decrease target (more leading 0's)
- This simulates real Bitcoin's difficulty

### Transaction Not Appearing

**Check**:
1. Transaction in mempool? `curl http://localhost:8001/mempool`
2. Transaction valid? Check node logs
3. UTXOs exist? `mini-bitcoin-py utxos <address>`
4. Sufficient balance? `mini-bitcoin-py balance <address>`

### "UTXO not found" Error

**Causes**:
- UTXO was already spent
- Transaction references wrong `prev_txid` or `prev_index`
- Chain was reorged and UTXO doesn't exist in current chain

**Solution**: Rebuild UTXO set or check transaction history

---

## 🗺️ Roadmap / Next Steps

### Planned Features

- [ ] **Persistent UTXO Index**: Avoid rebuilding on every startup
- [ ] **WebSocket Support**: Real-time transaction/block notifications
- [ ] **Light Client Mode**: SPV with Merkle proofs
- [ ] **Better Reorg Handling**: Incremental UTXO updates instead of full rebuild
- [ ] **Transaction Fee Estimation**: Dynamic fee calculation
- [ ] **Multi-threaded Mining**: Parallel nonce search
- [ ] **GraphQL API**: Alternative to REST
- [ ] **Web Dashboard**: Browser-based node management

### Ideas for Contribution

- Performance optimizations (Cython, numba)
- Additional test coverage
- Documentation improvements
- Docker improvements (health checks, monitoring)
- CI/CD pipeline setup
- Example scripts and tutorials

---

## 🤝 Contributing

Contributions are welcome! Here's how to help:

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/amazing-feature`
3. **Make** your changes (with tests!)
4. **Run** tests and linting: `pytest && ruff check . && black .`
5. **Commit** with clear messages: `git commit -m "Add amazing feature"`
6. **Push** to your fork: `git push origin feature/amazing-feature`
7. **Open** a Pull Request

### Code Style

- Follow PEP 8 (enforced by `ruff`)
- Use type hints where possible
- Write docstrings for public functions
- Keep functions focused and testable

### Testing

- Add tests for new features
- Maintain or improve coverage
- Test edge cases and error conditions

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Bitcoin Core** - For the original design and concepts
- **Python Cryptography Community** - For excellent libraries (`coincurve`, `ecdsa`)
- **FastAPI** - For the excellent async web framework
- **All Contributors** - Thanks for making this project better!

---

## 📚 Learn More

- **Bitcoin Whitepaper**: [bitcoin.org/bitcoin.pdf](https://bitcoin.org/bitcoin.pdf)
- **Mastering Bitcoin**: [github.com/bitcoinbook](https://github.com/bitcoinbook/bitcoinbook)
- **Bitcoin Developer Guide**: [bitcoin.org/en/developer-guide](https://bitcoin.org/en/developer-guide)

---

**Built with ❤️ for learning and experimentation.**

*Questions? Open an issue or start a discussion!*

