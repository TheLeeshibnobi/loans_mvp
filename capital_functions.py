from supabase import create_client, Client
import datetime
import os
import logging

from flask import send_file, make_response
import io
import tempfile
import os
import pandas
from datetime import datetime


# Set up logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


class CapitalFunctions:
    def __init__(self):
        try:
            url = os.getenv("SUPABASE_URL")
            service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

            if not url or not service_role_key:
                raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

            self.supabase: Client = create_client(url, service_role_key)
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise

    def owners(self):
        """returns a list of owners from the owner's table"""
        try:
            response = (
                self.supabase
                .table('owners')
                .select('user_name')
                .execute()
            )

            # Check for database errors
            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error in owners(): {response.error}")
                return []

            data = response.data or []

            if not data:
                return []

            # Safely extract usernames
            owners = []
            for owner in data:
                if owner and isinstance(owner, dict) and owner.get('user_name'):
                    owners.append(owner['user_name'])

            return owners

        except Exception as e:
            logger.error(f"Error in owners(): {e}")
            return []

    def get_owner_id(self, user_name):
        """Returns the owner id"""
        try:
            if not user_name or not isinstance(user_name, str):
                logger.warning("Invalid user_name provided to get_owner_id")
                return None

            # Get an owner id from chosen name
            owner_response = (
                self.supabase
                .table('owners')
                .select('id')
                .eq('user_name', user_name)
                .execute()
            )

            # Check for database errors
            if hasattr(owner_response, 'error') and owner_response.error:
                logger.error(f"Database error in get_owner_id: {owner_response.error}")
                return None

            if not owner_response.data:
                logger.warning(f"Owner with user_name '{user_name}' not found")
                return None

            owner_id = owner_response.data[0].get('id')
            if not owner_id:
                logger.warning(f"Owner ID not found for user_name '{user_name}'")
                return None

            return owner_id

        except Exception as e:
            logger.error(f"Error getting owner ID: {e}")
            return None

    def upload_transaction_file(self, transaction_file_obj, owner_id):
        """Uploads the transaction file to the Supabase bucket and returns the file URL."""
        try:
            if not transaction_file_obj or not owner_id:
                logger.warning("Invalid parameters provided to upload_transaction_file")
                return None

            # Validate file object
            if not hasattr(transaction_file_obj, 'filename') or not transaction_file_obj.filename:
                logger.warning("Invalid file object provided")
                return None

            # Get owner name
            owner_response = (
                self.supabase
                .table('owners')
                .select('user_name')
                .eq('id', owner_id)
                .execute()
            )

            # Check for database errors
            if hasattr(owner_response, 'error') and owner_response.error:
                logger.error(f"Database error in upload_transaction_file: {owner_response.error}")
                return None

            if not owner_response.data:
                logger.warning(f"Owner not found for ID: {owner_id}")
                return None

            owner_user_name = owner_response.data[0].get('user_name')
            if not owner_user_name:
                logger.warning(f"Owner user_name not found for ID: {owner_id}")
                return None

            # Construct filename safely
            filename_parts = transaction_file_obj.filename.split('.')
            if len(filename_parts) < 2:
                logger.warning("File has no extension")
                return None

            file_extension = filename_parts[-1]
            filename = f"equity_transactions/user_{owner_user_name}.{file_extension}"

            # Read file content safely
            try:
                file_bytes = transaction_file_obj.read()
                if not file_bytes:
                    logger.warning("File is empty")
                    return None
            except Exception as e:
                logger.error(f"Error reading file: {e}")
                return None

            # Reset file pointer for potential re-reading
            try:
                transaction_file_obj.seek(0)
            except Exception as e:
                logger.warning(f"Could not reset file pointer: {e}")

            # Get content type safely
            content_type = getattr(transaction_file_obj, 'content_type', 'application/octet-stream')

            # Upload the file
            try:
                upload_response = self.supabase.storage.from_('equity').upload(
                    filename,
                    file_bytes,
                    {"content-type": content_type}
                )

                # Check for upload errors
                if hasattr(upload_response, 'error') and upload_response.error:
                    logger.error(f"Storage upload error: {upload_response.error}")
                    return None

            except Exception as e:
                logger.error(f"Error uploading file to storage: {e}")
                return None

            # Get the public URL
            try:
                public_url = self.supabase.storage.from_('equity').get_public_url(filename)
                return public_url
            except Exception as e:
                logger.error(f"Error getting public URL: {e}")
                return None

        except Exception as e:
            logger.error(f"Error uploading transaction file: {e}")
            return None

    def record_given_dividend(self, amount, status, user_name, transaction_file_obj=None):
        """Registers a dividend in the disbursement table, with error handling."""
        try:
            # Validate inputs
            if not amount or not status or not user_name:
                logger.warning("Invalid parameters provided to record_given_dividend")
                return None

            # Validate amount
            try:
                float_amount = float(amount)
                if float_amount <= 0:
                    logger.warning(f"Invalid amount provided: {amount}")
                    return None
            except (ValueError, TypeError):
                logger.warning(f"Cannot convert amount to float: {amount}")
                return None

            transaction_files_urls = None

            # Get owner_id
            owner_id = self.get_owner_id(user_name)
            if not owner_id:
                logger.warning(f"Could not get owner_id for user_name: {user_name}")
                return None

            # Upload transaction_file file if provided
            if transaction_file_obj:
                transaction_files_urls = self.upload_transaction_file(transaction_file_obj, owner_id)
                if transaction_files_urls:
                    logger.info(f"Transaction file uploaded: {transaction_files_urls}")

            # Upload to disbursement table
            data = {
                'owner_id': owner_id,
                'amount': float_amount,
                'status': status
            }

            disbursement_response = self.supabase.table('disbursements').insert(data).execute()

            # Check for database errors
            if hasattr(disbursement_response, 'error') and disbursement_response.error:
                logger.error(f"Database error in disbursements insert: {disbursement_response.error}")
                return None

            # Upload to the equity_files table if file was uploaded
            if transaction_files_urls:
                try:
                    equity_files_data = {
                        'transaction_type': 'disbursement',
                        'files': transaction_files_urls,
                        'owner_id': owner_id
                    }

                    equity_files_response = self.supabase.table('equity_files').insert(equity_files_data).execute()

                    # Check for database errors
                    if hasattr(equity_files_response, 'error') and equity_files_response.error:
                        logger.error(f"Database error in equity_files insert: {equity_files_response.error}")
                        # Don't return None here as the main operation succeeded

                except Exception as e:
                    logger.error(f"Error inserting into equity_files: {e}")
                    # Don't return None here as the main operation succeeded

            logger.info(f"Dividend recorded successfully for {user_name}")
            return disbursement_response

        except Exception as e:
            logger.error(f"Error while recording dividend: {e}")
            return None

    def record_capital_injection(self, user_name, amount, status, transaction_file_obj=None):
        """Records a capital injection into the injection table in the database"""
        try:
            # Validate inputs
            if not user_name or not amount or not status:
                logger.warning("Invalid parameters provided to record_capital_injection")
                return None

            # Validate amount
            try:
                float_amount = float(amount)
                if float_amount <= 0:
                    logger.warning(f"Invalid amount provided: {amount}")
                    return None
            except (ValueError, TypeError):
                logger.warning(f"Cannot convert amount to float: {amount}")
                return None

            transaction_files_urls = None

            # Get owner_id
            owner_id = self.get_owner_id(user_name)
            if not owner_id:
                logger.warning(f"Could not get owner_id for user_name: {user_name}")
                return None

            # Upload transaction_file file if provided
            if transaction_file_obj:
                transaction_files_urls = self.upload_transaction_file(transaction_file_obj, owner_id)
                if transaction_files_urls:
                    logger.info(f"Transaction file uploaded: {transaction_files_urls}")

            # Insert into injections table
            data = {
                'owner_id': owner_id,
                'amount': float_amount,
                'status': status
            }

            response = self.supabase.table('injections').insert(data).execute()

            # Check for database errors
            if hasattr(response, 'error') and response.error:
                logger.error(f"Database error in injections insert: {response.error}")
                return None

            # Upload to the equity_files table if file was uploaded
            if transaction_files_urls:
                try:
                    equity_files_data = {
                        'transaction_type': 'injection',
                        'files': transaction_files_urls,
                        'owner_id': owner_id
                    }

                    equity_files_response = self.supabase.table('equity_files').insert(equity_files_data).execute()

                    # Check for database errors
                    if hasattr(equity_files_response, 'error') and equity_files_response.error:
                        logger.error(f"Database error in equity_files insert: {equity_files_response.error}")
                        # Don't return None here as the main operation succeeded

                except Exception as e:
                    logger.error(f"Error inserting into equity_files: {e}")
                    # Don't return None here as the main operation succeeded

            logger.info(f"Capital injection recorded successfully for {user_name}")
            return response

        except Exception as e:
            logger.error(f"Error while recording capital injection: {e}")
            return None

    def capital_transactions(self, range):
        """Returns the recent capital transactions with owner names."""

        try:
            # Step 1: Fetch capital transactions
            response = (
                self.supabase
                .table('capital_transactions')
                .select('*')
                .order('created_at', desc=True)
                .limit(range)
                .execute()
            )

            data = response.data if hasattr(response, 'data') else []

            if not data:
                print("No capital transactions found.")
                return []

            # Step 2: Replace owner_id with user_name
            enriched_data = []
            for transaction in data:
                owner_id = transaction.get('owner_id')

                owner_response = (
                    self.supabase
                    .table('owners')
                    .select('user_name')
                    .eq('id', owner_id)
                    .limit(1)
                    .execute()
                )

                # Default to owner_id if no user_name found
                user_name = (
                    owner_response.data[0]['user_name']
                    if owner_response.data
                    else owner_id
                )

                transaction['owner_name'] = user_name
                transaction.pop('owner_id', None)  # Remove owner_id if you only want name
                enriched_data.append(transaction)

            return enriched_data

        except Exception as e:
            print(f'Exception while fetching capital transactions: {e}')
            return []

    def get_transactions(self, start_date=None, end_date=None, user_name=None, amount=None):
        """Returns capital transactions filtered by any combination of date range, username, and/or amount."""

        try:
            # Step 1: Start base query
            query = self.supabase.table('capital_transactions').select('*')

            if start_date:
                query = query.gte('created_at', start_date)
            if end_date:
                query = query.lte('created_at', end_date)

            # Step 2: Execute query
            response = query.execute()
            transactions = response.data if hasattr(response, 'data') else []

            if not transactions:
                print("No transactions found.")
                return []

            filtered_data = []

            for txn in transactions:
                owner_id = txn.get('owner_id')

                match_user = True
                match_amount = True

                # Step 3: Filter by user_name if provided
                if user_name:
                    owner_response = (
                        self.supabase
                        .table('owners')
                        .select('user_name')
                        .eq('id', owner_id)
                        .limit(1)
                        .execute()
                    )
                    if owner_response.data:
                        db_user_name = owner_response.data[0]['user_name']
                        match_user = db_user_name.lower() == user_name.lower()
                    else:
                        match_user = False

                # Step 4: Filter by amount if provided
                if amount is not None:
                    match_amount = float(txn.get('amount', 0)) == float(amount)

                # Step 5: Append if all matches are satisfied
                if match_user and match_amount:
                    if user_name:
                        txn['owner_name'] = user_name
                        txn.pop('owner_id', None)
                    filtered_data.append(txn)

            return filtered_data

        except Exception as e:
            print(f"Exception while fetching transactions: {e}")
            return []

    def obtain_csv_data(self, data):
        """Converts provided data to CSV format."""

        try:
            data_df = pandas.DataFrame(data)

            if data_df.empty:
                print("Warning: No data provided to convert.")
                return None

            data_csv = data_df.to_csv(index=False)  # Correct usage
            return data_csv

        except Exception as e:
            print(f"Error while converting data to CSV: {e}")
            return None


    def download_capital_transactions(self, start_date, end_date, user_name=None, amount=None):
        """Returns a Flask CSV download response of capital transactions."""

        try:
            # Step 1: Get filtered data
            data = self.get_transactions(start_date, end_date, user_name, amount)

            if not data:
                return make_response("No data available for the given filters.", 204)

            # Step 2: Convert to CSV using pandas
            csv_output = self.obtain_csv_data(data)

            # Step 3: Create a BytesIO object for the CSV
            csv_buffer = io.BytesIO()
            csv_buffer.write(csv_output.encode('utf-8'))
            csv_buffer.seek(0)

            # Step 4: Generate filename
            filename = f"capital_transactions_{start_date}_to_{end_date}.csv"

            # Step 5: Return file using send_file
            return send_file(
                csv_buffer,
                mimetype='text/csv',
                as_attachment=True,
                download_name=filename  # Use download_name instead of attachment_filename for newer Flask versions
            )

        except Exception as e:
            print(f"ERROR in download_capital_transactions: {e}")
            return make_response(f"Error generating CSV: {e}", 500)

    def total_injections(self, owner_id):
        """Gets the total capital injection for an owner"""
        try:
            injection_response = (
                self.supabase
                .table('injections')
                .select('amount')
                .eq('owner_id', owner_id)
                .execute()
            )

            total_injection = sum(float(row['amount']) for row in injection_response.data)
            return total_injection

        except Exception as e:
            print(f'Exception in total_injections: {e}')
            return 0.0

    def total_dividends(self, owner_id):
        """Gets the total capital injection for an owner"""
        try:
            injection_response = (
                self.supabase
                .table('disbursements')
                .select('amount')
                .eq('owner_id', owner_id)
                .execute()
            )

            total_injection = sum(float(row['amount']) for row in injection_response.data)
            return total_injection

        except Exception as e:
            print(f'Exception in total_injections: {e}')
            return 0.0

    def get_owners(self):
        """Returns a list of owners and their info, plus total capital injection and dividend payout."""

        try:
            owners_response = (
                self.supabase
                .table('owners')
                .select('*')
                .execute()
            )

            owners = owners_response.data

            for owner in owners:
                owner['total_invested'] = self.total_injections(owner['id'])

                owner['total_dividends'] = self.total_dividends(owner['id'])

                try:
                    dt = datetime.fromisoformat(
                        owner['created_at'].replace('Z', '+00:00'))  # Handle Zulu time if it exists
                    owner['created_at'] = dt.strftime('%Y-%m-%d')
                except Exception as e:
                    print(f"Error formatting date for owner {owner['id']}: {e}")
                    owner['created_at'] = owner['created_at']  # Keep original if conversion fails

            return owners

        except Exception as e:
            print(f'Exception in get_owners: {e}')
            return []

    def add_owner(self, user_name, email, phone, nrc):
        """Adds a new owner to the owners table."""

        data = {
            'user_name': user_name,
            'email': email,
            'phone': phone,
            'nrc_number': nrc
        }

        try:
            response = self.supabase.table('owners').insert(data).execute()
            print(f'Inserted owner: {response.data}')
            return response.data
        except Exception as e:
            print(f'Exception in add_owner: {e}')
            return None


