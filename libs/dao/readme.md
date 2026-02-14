# UROG DAO Library

Database access library for the UROG automation system with a tiered data architecture.

## Architecture

The database uses a three-tier normalization approach:

### Bronze Layer (Raw Data Ingestion)
Raw data from various sources stored as JSONB:
- Source name and type tracking
- Untouched raw payloads
- Processing status tracking

### Silver Layer (Normalized Core Data)
Cleaned, normalized data in proper relational tables:
- **People**: Students, professors, admins with flexible profile data
- **Opportunities**: Research positions, internships, events
- **Applications**: Links between people and opportunities

See [schema.sql](src/dao/schema.sql) for detailed table definitions.

### Automation Layer (Templates & Logs)
Communication automation infrastructure:
- **Templates**: Jinja-style message templates for email/WhatsApp
- **Sent Logs**: Audit trail of all sent messages

## Installation

### From source (development)
```bash
cd libs/dao
pip install -e .
```

### With dev dependencies (for testing)
```bash
pip install -e ".[dev]"
```

## Configuration

Set the `DATABASE_URL` environment variable:
```bash
export DATABASE_URL="postgresql://user:password@host:port/database"
```

Or use a `.env` file:
```
DATABASE_URL=postgresql://user:password@host:port/database
```

## Usage

### Basic Usage

```python
from dao import UrogDB

# Initialize with environment variable
db = UrogDB()

# Or with explicit connection string
db = UrogDB(connection_string="postgresql://...")

# Initialize schema (first time setup)
db.init_schema()
```

### Bronze Layer - Data Ingestion

```python
# Ingest raw data
inbox_id = db.ingest_raw(
    source_name="Fall Recruitment Form",
    source_type="google_form",
    payload={"name": "John Doe", "email": "john@example.com"}
)

# Get unprocessed items
items = db.get_unprocessed_inbox_items(limit=50)

# Mark as processed
db.mark_inbox_processed(inbox_id)

# Mark as failed
db.mark_inbox_processed(inbox_id, error="Invalid email format")
```

### Silver Layer - Core Data

```python
# Create or update a person
person_id = db.upsert_person(
    email="student@university.edu",
    full_name="Jane Smith",
    role="student",
    phone="+1234567890",
    extra_data={"major": "CS", "year": 3, "gpa": 3.8}
)

# Create an opportunity
opp_id = db.create_opportunity(
    title="AI Research Assistant",
    owner_id=professor_id,
    description="Machine learning research position",
    type="research"
)
```

### Automation Layer - Messaging

```python
# Get a template
template = db.get_template("welcome_email")

# Log a sent message
db.log_sent_message(
    recipient_id=person_id,
    template_id=template['id'],
    platform="email",
    compiled_msg="Hello John, welcome to UROG!",
    status="sent"
)

# Log a failed message
db.log_sent_message(
    recipient_id=person_id,
    template_id=template['id'],
    platform="whatsapp",
    compiled_msg="Failed message",
    status="failed",
    error="Invalid phone number"
)
```

### Using the Singleton

```python
from dao import db

# The 'db' singleton is pre-configured from environment
db.connect()
people = db.get_unprocessed_inbox_items()
db.close()
```

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=dao --cov-report=html

# Run specific test file
pytest tests/test_connection.py

# Run specific test
pytest tests/test_bronze_layer.py::TestBronzeLayer::test_ingest_raw_inserts_data

# Run with verbose output
pytest -v
```

The test suite includes:
- **test_connection.py**: Connection management and schema initialization
- **test_bronze_layer.py**: Data ingestion and inbox operations
- **test_silver_layer.py**: People and opportunity operations
- **test_automation.py**: Template and message logging operations
- **test_integration.py**: End-to-end workflow scenarios

All tests use mocked database connections, so no actual database is required.

## Development

### Project Structure
```
libs/dao/
├── pyproject.toml          # Package configuration
├── readme.md               # This file
├── src/
│   └── dao/
│       ├── __init__.py     # Package exports
│       ├── client.py       # Main UrogDB class
│       └── schema.sql      # Database schema
└── tests/
    ├── conftest.py         # Pytest fixtures
    ├── test_*.py           # Test modules
    └── __init__.py
```

### Adding New Features

1. Add methods to `UrogDB` class in [client.py](src/dao/client.py)
2. Write tests in the appropriate test file
3. Update this README with usage examples
4. Run tests to ensure everything works

## License

Internal UROG project. 