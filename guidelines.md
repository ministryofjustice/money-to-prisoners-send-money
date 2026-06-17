# Prisoner Money Send Money Development Guidelines

## Project Overview and Core Functions

The Prisoner Money Send Money application is the public-facing site where family and friends can send money to someone in prison. It allows users to make payments using a debit card (via GOV.UK Pay) or get details for a bank transfer.

### Core Functionalities
- **Prisoner Lookup**: Validates prisoner details (number and date of birth) before allowing a payment.
- **Debit Card Payments**: Integrates with GOV.UK Pay to facilitate secure online payments.
- **Bank Transfer Information**: Provides users with the necessary details (account number, sort code, and reference) to make a bank transfer.
- **Payment Tracking**: Monitors the status of card payments and handles successful, failed, or cancelled transactions.
- **Service Availability Check**: Checks if the payment service is available before allowing users to start the process.
- **Incomplete Payment Reconciliation**: Background tasks reconcile payments that were started but not finished (e.g., due to browser closure).

## Application Architecture

The project is built with **Django** and relies on the `money-to-prisoners-api` for its data and core business logic. It also integrates with **GOV.UK Pay** for payment processing and **GOV.UK Notify** for sending confirmation emails.

### API Interaction and Calls

The application interacts with the `money-to-prisoners-api` using shared credentials and OAuth2 authentication. Key API calls include:

- **Service Status**:
  - `GET /service-availability/`: Checks if the overall service and GOV.UK Pay are available.
  - `GET /healthcheck.json`: Used for monitoring the health of the API.

- **Prisoner Information**:
  - `GET /prisoner_validity/`: Validates that a prisoner exists with the provided number and date of birth.
  - `GET /prisoner_account_balances/{prisoner_number}`: Checks the current balance of a prisoner's account to enforce payment limits (capping).

- **Payment Management**:
  - `POST /payments/`: Creates a new payment record in the MTP system.
  - `GET /payments/`: Retrieves payments (e.g., to find and process incomplete ones).
  - `GET /payments/{uuid}/`: Retrieves details for a specific payment.
  - `PATCH /payments/{uuid}/`: Updates a payment record with the GOV.UK Pay reference, status updates, or sender details.

- **Performance and Reporting**:
  - `GET /performance/data/`: Fetches performance metrics for the public performance dashboard.

### External Integrations

- **GOV.UK Pay**:
  - `POST /payments`: Creates a payment on GOV.UK Pay.
  - `GET /payments/{govuk_id}`: Retrieves the status of a payment from GOV.UK Pay.
  - `POST /payments/{govuk_id}/capture`: Captures a delayed payment.
  - `POST /payments/{govuk_id}/cancel`: Cancels a payment.
- **GOV.UK Notify**: Used to send confirmation emails to the person sending the money.
- **Zendesk**: Used to submit help and feedback tickets.

## Background Tasks

- **`update_incomplete_payments`**: This management command should be run periodically (e.g., via a cron job). It:
  - Fetches incomplete payments from the MTP API (`GET /payments/`).
  - Checks their status on GOV.UK Pay.
  - Updates the MTP API with the final status (`taken`, `failed`, `rejected`, etc.).
  - Sends confirmation or failure emails to the sender as appropriate.

## Key Project Apps

- **`send_money` (`mtp_send_money.apps.send_money`)**: The primary application containing the payment flow, prisoner lookup, and payment processing logic.
- **`help_area` (`mtp_send_money.apps.help_area`)**: Manages the help pages and feedback forms.
- **`mtp_common`**: A shared library used across all MTP projects for consistent styling, utilities, authentication, and common logic.

## Build and Configuration

- **Environment**: Requires Python 3.12+ and Node.js 24+.
- **Virtual Environment**: Use a Python virtual environment to isolate dependencies.
  ```shell
  python3 -m venv venv
  source venv/bin/activate
  ```
- **Dependencies**: Managed via `run.py`. To update all dependencies:
  ```shell
  ./run.py dependencies
  ```
- **Configuration**:
  - The application connects to the API (default `http://localhost:8000`).
  - It uses `SHARED_API_USERNAME` and `SHARED_API_PASSWORD` to authenticate with the API (defined in environment variables or settings).
  - Local settings can be overridden in `mtp_send_money/settings/local.py` (copy from `local.py.sample`).
- **Management Script**: `run.py` is the primary interface for development tasks.
  - `./run.py serve`: Start development server with live-reload (BrowserSync on `:3004`, Django on `:8004`).
  - `./run.py start`: Start development server without live-reload.
  - `./run.py --verbosity 2 help`: List all available build tasks.

## Testing

### Running Tests
- **Full Suite**: Use `./run.py test`. This includes building assets and running Django tests.
- **Django Tests Only**: For faster feedback during development, run `manage.py test` directly:
  ```shell
  ./manage.py test send_money
  ./manage.py test mtp_send_money.apps.<app>.tests.<test_module>
  ```

### Adding New Tests
- Tests are located in `mtp_send_money/apps/<app_name>/tests/`.
- Use standard Django `TestCase` or `SimpleTestCase`.
- Functional tests often use `responses` library to mock API calls.

## Additional Development Information

- **Frontend Assets**:
  - Assets are located in `assets-src/`.
  - Built assets are placed in `assets/`.
  - Use `./run.py build` to compile assets (SASS and JavaScript).
- **Translations**:
  - Update messages with `./run.py make_messages`.
  - Sync with Transifex via `./run.py translations --pull` or `--push`.
- **Code Style**:
  - Follow PEP8 and Django coding conventions.
  - Linting can be checked via `./run.py lint`.
- **Docker**:
  - A Docker environment is available for local testing that mirrors production: `./run.py local_docker`.
