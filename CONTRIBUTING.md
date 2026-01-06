# Contributing to MiniBitcoinPy

Thank you for your interest in contributing to MiniBitcoinPy! 🎉

This document provides guidelines and instructions for contributing to the project. Whether you're fixing bugs, adding features, improving documentation, or reporting issues, your contributions are valuable.

---

## 📋 Table of Contents

- [Welcome](#welcome)
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Quality Standards](#quality-standards)
- [Testing](#testing)
- [Git Workflow](#git-workflow)
- [Pull Request Process](#pull-request-process)
- [Security Policy](#security-policy)
- [Consensus & Crypto Contributions](#consensus--crypto-contributions)

---

## 👋 Welcome

### Scope of Contributions

We welcome contributions in many forms:

- **🐛 Bug Reports**: Found a bug? Help us fix it!
- **✨ Features**: New functionality that aligns with the project goals
- **📚 Documentation**: Improvements to README, code comments, or guides
- **🧪 Tests**: Additional test coverage or test improvements
- **🔧 Code Quality**: Refactoring, performance improvements, type hints
- **🎨 UI/UX**: CLI improvements, better error messages, user experience
- **🔒 Security**: Responsible disclosure of security issues (see [Security Policy](#security-policy))

> **Note**: This is an educational project. Contributions should focus on clarity, correctness, and learning value rather than production-scale optimizations.

---

## 📜 Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

**In short:**
- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Respect different viewpoints and experiences

We are committed to providing a welcoming and harassment-free environment for all contributors.

---

## 🚀 Getting Started

### Prerequisites

Before you begin, ensure you have:

- **Python 3.11+** (check with `python --version`)
- **Docker & Docker Compose** (for multi-node testing)
- **Git** (for version control)
- **PostgreSQL 15+** (optional, if running without Docker)

### Quick Setup

1. **Fork and clone the repository**:

```bash
git clone https://github.com/your-username/mini-bitcoin-py.git
cd mini-bitcoin-py
```

2. **Create a virtual environment**:

```bash
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate
```

3. **Install dependencies**:

```bash
# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

This installs:
- The package itself (`mini_bitcoin_py`)
- Development tools (pytest, ruff, black, mypy)
- All runtime dependencies

4. **Verify installation**:

```bash
mini-bitcoin-py --help
pytest --version
ruff --version
```

---

## 🛠️ Development Setup

### Option 1: Docker Compose (Recommended for Multi-Node Testing)

Start PostgreSQL and 3 nodes:

```bash
docker-compose -f docker/docker-compose.yml up -d
```

This starts:
- **PostgreSQL** on port `5432`
- **Node 1** on port `8001` (http://localhost:8001)
- **Node 2** on port `8002` (http://localhost:8002)
- **Node 3** on port `8003` (http://localhost:8003)

Check status:

```bash
curl http://localhost:8001/health
```

Stop everything:

```bash
docker-compose -f docker/docker-compose.yml down
```

### Option 2: Local Development (Single Node)

1. **Set up PostgreSQL**:

```bash
# Create database
createdb minibitcoinpy

# Or use the init script
psql -U postgres -f docker/init-db.sql
```

2. **Create `.env` file**:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/minibitcoinpy
NODE_HOST=0.0.0.0
NODE_PORT=8000
NODE_NAME=dev-node
LOG_LEVEL=DEBUG
DEFAULT_TARGET=0x00000fffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
BLOCK_REWARD=5000000000
```

3. **Run migrations**:

```bash
alembic upgrade head
```

4. **Start the node**:

```bash
mini-bitcoin-py node --port 8000
```

---

## ⚙️ Environment Variables

The project uses environment variables for configuration. Create a `.env` file in the project root:

```env
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/minibitcoinpy

# Node Configuration
NODE_HOST=0.0.0.0
NODE_PORT=8000
NODE_NAME=dev-node

# Mining
DEFAULT_TARGET=0x00000fffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
BLOCK_REWARD=5000000000
MAX_BLOCK_TXS=100

# P2P Networking
BOOTSTRAP_PEERS=http://localhost:8001,http://localhost:8002
MAX_PEERS=50

# Logging
LOG_LEVEL=INFO
```

> **Tip**: For development, set `LOG_LEVEL=DEBUG` to see detailed logs.

---

## 💾 Database & Migrations

### Running Migrations

Apply all pending migrations:

```bash
alembic upgrade head
```

Rollback one migration:

```bash
alembic downgrade -1
```

### Creating a New Migration

1. **Auto-generate from model changes**:

```bash
alembic revision --autogenerate -m "add_new_table"
```

2. **Review the generated migration** in `mini_bitcoin_py/node/migrations/versions/`

3. **Edit if needed** (Alembic sometimes needs manual adjustments)

4. **Test the migration**:

```bash
# Rollback
alembic downgrade -1

# Apply
alembic upgrade head
```

### Tips for Schema Changes

- **Always test migrations** on a copy of production data (if applicable)
- **Never modify existing migrations** that have been applied to production
- **Add new migrations** for any schema changes
- **Consider backward compatibility** when removing columns

---

## 🏃 Running the Project

### Start a Node

```bash
mini-bitcoin-py node --port 8000
```

### Common Development Workflows

**Create a wallet**:

```bash
mini-bitcoin-py create-wallet
```

**Mine a block**:

```bash
mini-bitcoin-py mine --address <your_address> --node http://localhost:8000
```

**Send a transaction**:

```bash
mini-bitcoin-py send \
  --from <private_key> \
  --to <recipient_address> \
  --amount 1000000 \
  --node http://localhost:8000
```

**Check node status**:

```bash
mini-bitcoin-py status --node http://localhost:8000
```

**Run tests**:

```bash
pytest
```

**Format code**:

```bash
black .
ruff check --fix .
```

---

## ✅ Quality Standards

### Code Style

We use **Black** for formatting and **Ruff** for linting.

**Format code**:

```bash
black .
```

**Lint code**:

```bash
ruff check .
```

**Auto-fix linting issues**:

```bash
ruff check --fix .
```

**Configuration**: See `pyproject.toml` for Black and Ruff settings.

### Type Hints

**Type hints are required** in:
- All functions in `mini_bitcoin_py/core/`
- All functions in `mini_bitcoin_py/node/`
- Public API functions in `cli/`

**Type checking**:

```bash
mypy mini_bitcoin_py
```

**Example**:

```python
def validate_transaction(
    tx: Transaction,
    utxo_set: UTXOSet,
) -> ValidationResult:
    """Validate a transaction against the UTXO set."""
    ...
```

### Testing Requirements

- **All new features must include tests**
- **Bug fixes must include regression tests**
- **Aim for >80% code coverage** (especially in `core/`)
- **Tests should be fast and isolated**

### Logging & Error Handling

- **Use structured logging** with appropriate levels:
  - `DEBUG`: Detailed information for debugging
  - `INFO`: General informational messages
  - `WARNING`: Warning messages (e.g., peer connection failures)
  - `ERROR`: Error messages (e.g., validation failures)
  - `CRITICAL`: Critical errors (e.g., database connection lost)

- **Handle errors gracefully**:
  - Return `ValidationResult` objects instead of raising exceptions where appropriate
  - Provide clear error messages
  - Log errors with context

**Example**:

```python
import logging

logger = logging.getLogger(__name__)

def process_block(block: Block) -> bool:
    try:
        result = validate_block(block)
        if not result.valid:
            logger.error(f"Block validation failed: {result.message}")
            return False
        return True
    except Exception as e:
        logger.exception(f"Unexpected error processing block: {e}")
        return False
```

---

## 🧪 Testing

### Running Tests

**All tests**:

```bash
pytest
```

**With coverage**:

```bash
pytest --cov=mini_bitcoin_py --cov-report=html
```

**Specific test file**:

```bash
pytest tests/test_utxo_rules.py -v
```

**Specific test**:

```bash
pytest tests/test_utxo_rules.py::TestUTXOSet::test_add_and_get -v
```

**Fast tests only** (skip slow integration tests):

```bash
pytest -m "not slow"
```

### Test Structure

- **Unit tests**: Test individual functions/classes in isolation
- **Integration tests**: Test components working together (may require PostgreSQL)

**Test file naming**: `test_<module_name>.py`

**Test class naming**: `Test<ClassName>`

**Example**:

```python
class TestUTXOSet:
    def test_add_and_get(self):
        utxo_set = UTXOSet()
        txout = TxOut(amount=1000, pubkey_hash="ab" * 20)
        utxo_set.add("txid1", 0, txout)
        result = utxo_set.get("txid1", 0)
        assert result == txout
```

### Integration Tests with PostgreSQL

Some tests require a running PostgreSQL instance:

```bash
# Start PostgreSQL (via Docker)
docker run -d --name test-postgres \
  -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=test_db \
  -p 5433:5432 \
  postgres:15-alpine

# Set test database URL
export DATABASE_URL=postgresql://postgres:test@localhost:5433/test_db

# Run tests
pytest tests/test_integration.py
```

---

## 🔍 Linting & Formatting

### Ruff (Linting)

**Check for issues**:

```bash
ruff check .
```

**Auto-fix issues**:

```bash
ruff check --fix .
```

**Check specific path**:

```bash
ruff check mini_bitcoin_py/core/
```

### Black (Formatting)

**Format all files**:

```bash
black .
```

**Check without formatting**:

```bash
black --check .
```

**Format specific file**:

```bash
black mini_bitcoin_py/core/block.py
```

### Pre-commit Hooks (Recommended)

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.1.1
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.14
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
```

**Install pre-commit**:

```bash
pip install pre-commit
pre-commit install
```

**Run manually**:

```bash
pre-commit run --all-files
```

---

## 🌿 Git Workflow

### Branch Naming

Use descriptive branch names with prefixes:

- `feature/` - New features (e.g., `feature/add-merkle-proofs`)
- `fix/` - Bug fixes (e.g., `fix/utxo-double-spend-check`)
- `chore/` - Maintenance tasks (e.g., `chore/update-dependencies`)
- `docs/` - Documentation updates (e.g., `docs/add-api-examples`)
- `test/` - Test improvements (e.g., `test/add-integration-tests`)

**Example**:

```bash
git checkout -b feature/add-transaction-fee-estimation
```

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

**Format**:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test additions/changes
- `chore`: Maintenance tasks

**Examples**:

```
feat(core): add transaction fee estimation

Implement fee estimation based on mempool size and recent block fees.
Includes unit tests and integration with CLI.

Closes #123
```

```
fix(node): correct UTXO set rebuild on chain reorg

When a chain reorg occurs, the UTXO set was not being properly
rebuilt. This fix ensures all UTXOs are correctly restored.

Fixes #456
```

### Keeping PRs Small

- **One feature/fix per PR**
- **Keep changes focused** (don't mix refactoring with new features)
- **Break large features into smaller PRs** when possible
- **Keep PRs under 500 lines** when possible (exceptions for large refactors)

---

## 🔄 Pull Request Process

### Before Submitting

1. **Ensure tests pass**:

```bash
pytest
```

2. **Run linting and formatting**:

```bash
black .
ruff check --fix .
mypy mini_bitcoin_py
```

3. **Update documentation** if your changes affect:
   - API endpoints
   - CLI commands
   - Configuration options
   - Architecture

4. **Add/update tests** for new features or bug fixes

5. **Check migration files** if you changed the database schema

### PR Checklist

When creating a PR, ensure:

- [ ] Tests pass locally (`pytest`)
- [ ] Code is formatted (`black .`)
- [ ] Linting passes (`ruff check .`)
- [ ] Type checking passes (`mypy mini_bitcoin_py`)
- [ ] Documentation is updated (README, docstrings, etc.)
- [ ] Migration files are included (if schema changed)
- [ ] Commit messages follow Conventional Commits
- [ ] PR description explains the change and motivation
- [ ] Screenshots/logs included for behavior changes (if applicable)

### PR Description Template

```markdown
## Description
Brief description of the changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
How was this tested?

## Checklist
- [ ] Tests pass
- [ ] Code formatted
- [ ] Documentation updated
- [ ] Migration included (if needed)
```

### Review Expectations

- **Be patient**: Maintainers are volunteers
- **Respond to feedback**: Address review comments promptly
- **Keep discussions constructive**: Focus on code, not people
- **Update PRs** based on feedback (don't create new PRs)

---

## 🐛 Issue Guidelines

### Bug Reports

**Use this template**:

```markdown
**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce:
1. Run command '...'
2. See error

**Expected behavior**
What you expected to happen.

**Actual behavior**
What actually happened.

**Environment**
- OS: [e.g., Windows 11, Ubuntu 22.04]
- Python version: [e.g., 3.11.5]
- Package version: [e.g., 0.1.0]

**Logs**
Paste relevant logs here.

**Additional context**
Any other relevant information.
```

### Feature Requests

**Use this template**:

```markdown
**Motivation**
Why is this feature needed?

**Proposal**
Describe the feature in detail.

**Alternatives**
What alternatives have you considered?

**Additional context**
Any other relevant information.
```

---

## 🔒 Security Policy

### Reporting Security Issues

**⚠️ IMPORTANT: Do NOT open public issues for security vulnerabilities.**

Security issues should be reported **privately** to: `security@example.com` (replace with actual email)

**Include in your report**:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

**Response time**: We aim to respond within 48 hours and provide updates every 7 days.

### Security-Sensitive Areas

The following areas require extra care:

- **Consensus rules** (block/transaction validation)
- **Cryptographic operations** (signing, hashing, key derivation)
- **UTXO set management** (double-spend prevention)
- **Chain synchronization** (reorg handling)
- **P2P networking** (message validation)

> **Note**: Consensus and crypto bugs can have serious implications. Always test thoroughly and consider backward compatibility.

---

## ⚠️ Consensus & Crypto Contributions

Contributions to consensus or cryptographic code require **extra care** due to their critical nature.

### Deterministic Serialization

**All hashing must use deterministic byte encoding**, not JSON or dict representations.

**✅ Correct**:

```python
def serialize(self) -> bytes:
    return (
        encode_int32(self.version)
        + encode_fixed_bytes(self.prev_hash, 32)
        + encode_uint32(self.timestamp)
    )
```

**❌ Incorrect**:

```python
def serialize(self) -> bytes:
    return json.dumps(self.to_dict()).encode()  # NOT deterministic!
```

### Test Vectors

**Changes to hashing or signing must include test vectors**:

```python
def test_block_hash_deterministic():
    """Test that block hash is deterministic."""
    header = BlockHeader(...)
    hash1 = header.compute_hash()
    hash2 = header.compute_hash()
    assert hash1 == hash2

def test_transaction_signing():
    """Test transaction signing with known test vector."""
    # Use known inputs and verify expected signature
    ...
```

### Backward Compatibility

**Avoid breaking changes to**:
- Transaction ID (txid) format
- Block hash format
- Signature format
- Address format

**If breaking changes are necessary**:
- Add a version field
- Support both old and new formats during transition
- Document the migration path

### Review Process

Consensus/crypto PRs will:
- Receive **extra scrutiny** during review
- Require **multiple approvals** from maintainers
- Need **comprehensive test coverage**
- Include **test vectors** for verification

---

## 📚 Documentation Contributions

### Where Documentation Lives

- **README.md**: Project overview, quickstart, usage
- **CONTRIBUTING.md**: This file
- **Code docstrings**: Function/class documentation
- **Inline comments**: Complex logic explanations

### Documentation Style

- **Use clear, concise language**
- **Include code examples** where helpful
- **Keep examples up-to-date** with code changes
- **Use markdown formatting** (headers, code blocks, lists)

**Example docstring**:

```python
def validate_transaction(
    tx: Transaction,
    utxo_set: UTXOSet,
) -> ValidationResult:
    """
    Validate a transaction against the UTXO set.

    Checks:
    - All inputs reference existing UTXOs
    - No double-spends
    - Valid signatures
    - Input sum >= output sum

    Args:
        tx: Transaction to validate
        utxo_set: Current UTXO set

    Returns:
        ValidationResult with validity and fee

    Raises:
        ValueError: If transaction structure is invalid
    """
    ...
```

---

## 🗺️ Project Roadmap & Good First Issues

### Roadmap

See the [README.md](README.md#roadmap--next-steps) for planned features.

### Good First Issues

Looking for a place to start? Try these:

- **Documentation improvements**: Fix typos, clarify explanations, add examples
- **Test coverage**: Add tests for edge cases or untested code paths
- **CLI improvements**: Better error messages, help text, or UX enhancements
- **Code quality**: Add type hints, improve docstrings, refactor for clarity
- **Bug fixes**: Check the issue tracker for "good first issue" labels

**Labeled issues**: Look for issues tagged with `good-first-issue` in the issue tracker.

---

## 📄 License

By contributing to MiniBitcoinPy, you agree that your contributions will be licensed under the **MIT License**.

---

## 🙏 Thank You!

Thank you for taking the time to contribute to MiniBitcoinPy! Your efforts help make this project better for everyone.

**Questions?** Open a discussion or reach out to maintainers.

**Happy coding!** 🚀

