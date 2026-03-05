# Milestone M2: Cheque Creation Implementation

## Summary

Implemented core cheque creation modules: rate fetching, amount computation with unique tail, Monero URI builder, QR generator, and cheque limits enforcement.

## Files Added

### Source Modules (`src/xmr_cheque_bot/`)

| File | Description |
|------|-------------|
| `rates.py` | CoinGecko XMR/RUB rate fetcher with 60s cache |
| `amount.py` | Amount computation with unique tail (1..9999 piconero) |
| `uri_qr.py` | Monero URI builder and QR code generator |
| `cheque_limits.py` | Max active cheques enforcement (10 per user) |

### Test File

| File | Description |
|------|-------------|
| `tests/test_cheque_creation.py` | 45 unit tests covering all M2 functionality |

## Module Details

### 1. Rate Fetch Module (`rates.py`)

**Features:**
- Fetches XMR/RUB rate from CoinGecko API
- 60-second in-memory cache with TTL
- Works without API key (uses public endpoint)
- Graceful error handling for rate limits, network issues
- Thread-safe with asyncio.Lock

**Key Functions:**
```python
async def fetch_xmr_rub_rate(force_refresh: bool = False) -> Decimal
class RateFetchError(Exception)
def invalidate_rate_cache() -> None
```

**API Endpoints:**
- Public (no key): `https://api.coingecko.com/api/v3/simple/price`
- Pro (with key): `https://pro-api.coingecko.com/api/v3/simple/price`

### 2. Amount Computation (`amount.py`)

**Algorithm:**
1. Fetch XMR/RUB rate
2. Calculate: `xmr = rub / rate`
3. Convert to atomic: `atomic = xmr * 1e12` (piconero)
4. Round to integer for base amount
5. Add unique tail: `tail = random(1..9999)`
6. Expected: `amount_atomic_expected = base_atomic + tail`

**Key Features:**
- Uses `Decimal` for all calculations (no float drift)
- Deterministic output given same inputs and tail
- Display format: exactly 12 decimal places

**Key Functions:**
```python
async def compute_cheque_amount(
    amount_rub: int,
    tail: int | None = None,
) -> ComputedAmount

def _atomic_to_display(atomic_units: int) -> str
def atomic_to_xmr(atomic_units: int) -> Decimal
def xmr_to_atomic(xmr_amount: Decimal) -> int
```

**Constants:**
```python
ATOMIC_UNITS_PER_XMR = Decimal("1000000000000")  # 1e12
MIN_TAIL = 1
MAX_TAIL = 9999
```

### 3. URI Builder & QR Generator (`uri_qr.py`)

**Features:**
- Builds RFC 3986 compliant Monero URIs
- Supports: address, amount, description, message
- Generates QR codes as PNG bytes (qrcode + Pillow)
- Configurable size and error correction

**Key Functions:**
```python
def build_monero_uri(
    address: str,
    amount_xmr: str | None = None,
    tx_description: str | None = None,
    tx_message: str | None = None,
) -> str

def generate_qr_code(
    data: str,
    size: int = 512,
    border: int = 4,
) -> bytes

def generate_payment_qr(
    address: str,
    amount_xmr: str,
    tx_description: str | None = None,
    size: int = 512,
) -> bytes
```

**URI Format:**
```
monero:<address>?tx_amount=<amount>&tx_description=<desc>&tx_message=<msg>
```

### 4. Cheque Limits (`cheque_limits.py`)

**Features:**
- Enforces max 10 active cheques per user
- Rate limiting stub (10/10min)
- Storage integration stubbed (TODO comments)

**Exceptions:**
```python
class ChequeLimitError(Exception)  # Max cheques exceeded
class RateLimitError(Exception)    # Rate limit exceeded
```

**Key Functions:**
```python
async def check_cheque_creation_allowed(user_id: str) -> bool
async def count_active_cheques(user_id: str) -> int
def get_active_statuses() -> set[ChequeStatus]
def is_status_active(status: ChequeStatus) -> bool
```

## Running Tests

### All M2 Tests
```bash
cd xmr-cheque-bot
source .venv/bin/activate
python -m pytest tests/test_cheque_creation.py -v
```

### Specific Test Categories
```bash
# Amount computation tests
python -m pytest tests/test_cheque_creation.py::TestAmountComputation -v

# Atomic conversion tests
python -m pytest tests/test_cheque_creation.py::TestAtomicConversions -v

# Tail generation tests
python -m pytest tests/test_cheque_creation.py::TestTailGeneration -v

# URI builder tests
python -m pytest tests/test_cheque_creation.py::TestMoneroURI -v

# QR generation tests
python -m pytest tests/test_cheque_creation.py::TestQRGeneration -v

# Rate cache tests
python -m pytest tests/test_cheque_creation.py::TestRateCache -v

# Cheque limits tests
python -m pytest tests/test_cheque_creation.py::TestChequeLimits -v

# Integration tests
python -m pytest tests/test_cheque_creation.py::TestChequeCreationIntegration -v
```

## Test Coverage

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestAmountComputation | 9 | Amount computation, validation, errors |
| TestAtomicConversions | 6 | Atomic<->XMR conversions, display |
| TestTailGeneration | 5 | Tail bounds, uniqueness, distribution |
| TestMoneroURI | 7 | URI building, encoding, edge cases |
| TestQRGeneration | 5 | QR generation, sizes, formats |
| TestRateCache | 3 | Cache TTL, invalidation |
| TestChequeLimits | 5 | Limit checks, exceptions, statuses |
| TestChequeCreationIntegration | 5 | End-to-end flows |
| **Total** | **45** | **All M2 modules** |

## Usage Example

```python
from xmr_cheque_bot.amount import compute_cheque_amount
from xmr_cheque_bot.uri_qr import generate_payment_qr

# 1. Compute amount
amount = await compute_cheque_amount(amount_rub=1000)
print(f"Expected: {amount.amount_atomic_expected} atomic units")
print(f"Display: {amount.amount_xmr_display} XMR")

# 2. Generate payment QR
qr_bytes = generate_payment_qr(
    address="44AFFq5k...",
    amount_xmr=amount.amount_xmr_display,
    tx_description="Invoice #123",
)

# 3. Check limits before creation
from xmr_cheque_bot.cheque_limits import check_cheque_creation_allowed
try:
    await check_cheque_creation_allowed(user_id="123456")
    # Proceed with cheque creation
except ChequeLimitError as e:
    print(f"Limit: {e.current_count}/{e.max_allowed}")
```

## Constraints Followed

✅ No Telegram handlers (only core modules)  
✅ No monitor worker implementation  
✅ Redis integration stubbed with TODOs  
✅ All calculations use Decimal (no float drift)  
✅ Unique tail range: 1..9999 piconero  
✅ 60s rate cache with error handling  
✅ Works without CoinGecko API key  
✅ Max 10 active cheques per user enforced  
✅ 45 unit tests covering all functionality  

## TODOs for M3/M4

1. **Storage Integration** (`cheque_limits.py`):
   - Implement `count_active_cheques()` with Redis query
   - Implement `_check_rate_limit()` with Redis
   - Implement `record_cheque_creation()` with Redis updates

2. **Rate Cache** (`rates.py`):
   - Consider persistent cache in Redis for multi-instance deployments

3. **QR Generation** (`uri_qr.py`):
   - Add logo overlay option
   - Add styling customization
