from supabase import create_client, Client
from datetime import date, timedelta, datetime, UTC, timezone
from dotenv import load_dotenv
import os
import json
import logging
from typing import Optional, List, Dict, Any, Union

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LoansError(Exception):
    """Custom exception for Loans class errors"""
    pass


class Loans:
    """Contains metrics for the overview dashboard"""

    def __init__(self):
        try:
            # Load environment variables
            load_dotenv()

            url = os.getenv("SUPABASE_URL")
            service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

            if not url or not service_role_key:
                raise LoansError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set in environment variables.")

            self.supabase: Client = create_client(url, service_role_key)

            # Test connection
            self._test_connection()

        except Exception as e:
            logger.error(f"Failed to initialize Loans class: {str(e)}")
            raise LoansError(f"Initialization failed: {str(e)}")

    def _test_connection(self) -> None:
        """Test the Supabase connection"""
        try:
            # Simple query to test connection
            response = self.supabase.table('borrowers').select('id').limit(1).execute()
            logger.info("Supabase connection established successfully")
        except Exception as e:
            logger.error(f"Supabase connection test failed: {str(e)}")
            raise LoansError(f"Database connection failed: {str(e)}")

    def borrower_identity(self, borrower_id: Union[int, str]) -> Dict[str, str]:
        """Returns the name and NRC of that borrower"""

        if not borrower_id:
            logger.warning("borrower_identity called with empty borrower_id")
            return {'name': 'Unknown', 'nrc': 'Unknown'}

        try:
            response = (
                self.supabase
                .table('borrowers')
                .select('name, nrc_number')
                .eq('id', borrower_id)
                .execute()
            )

            # Check if response has data attribute
            if not hasattr(response, 'data') or response.data is None:
                logger.warning(f"No data attribute in response for borrower_id: {borrower_id}")
                return {'name': 'Unknown', 'nrc': 'Unknown'}

            # Handle empty results
            if not response.data or len(response.data) == 0:
                logger.warning(f"No borrower found with id: {borrower_id}")
                return {'name': 'Unknown', 'nrc': 'Unknown'}

            borrower_data = response.data[0]

            # Safely extract data with defaults
            name = borrower_data.get('name', 'Unknown')
            nrc = borrower_data.get('nrc_number', 'Unknown')

            return {
                'name': name if name else 'Unknown',
                'nrc': nrc if nrc else 'Unknown'
            }

        except Exception as e:
            logger.error(f"Error fetching borrower identity for id {borrower_id}: {str(e)}")
            return {'name': 'Unknown', 'nrc': 'Unknown'}

    def old_borrower_loan(self, borrower_id: Union[int, str], amount: float, transaction_costs: float,
                          interest_rate: float, duration_days: int, due_date: str,
                          contract_file_obj: Optional[Any] = None,
                          collateral_files_list: Optional[List[Any]] = None,
                          loan_reason: Optional[str] = None) -> Optional[int]:
        """Registers a loan for an already existing borrower in the database."""

        # Input validation
        if not borrower_id:
            logger.error("borrower_id is required")
            return None

        if not isinstance(amount, (int, float)) or amount <= 0:
            logger.error(f"Invalid amount: {amount}")
            return None

        if not isinstance(interest_rate, (int, float)) or interest_rate < 0:
            logger.error(f"Invalid interest_rate: {interest_rate}")
            return None

        if not isinstance(duration_days, int) or duration_days <= 0:
            logger.error(f"Invalid duration_days: {duration_days}")
            return None

        # Verify borrower exists
        borrower_check = self.borrower_identity(borrower_id)
        if borrower_check['name'] == 'Unknown':
            logger.error(f"Borrower with id {borrower_id} does not exist")
            return None

        contract_file_url = None
        collateral_file_urls = []

        try:
            # Upload contract file if provided
            if contract_file_obj:
                contract_file_url = self.upload_contract_file(contract_file_obj, borrower_id)
                if contract_file_url:
                    logger.info(f"Contract file uploaded: {contract_file_url}")
                else:
                    logger.warning("Contract file upload failed")

            # Upload collateral files if provided
            if collateral_files_list and len(collateral_files_list) > 0:
                collateral_file_urls = self.upload_collateral_files_list(collateral_files_list, borrower_id)
                if collateral_file_urls:
                    logger.info(f"Collateral files uploaded: {len(collateral_file_urls)} files")
                else:
                    logger.warning("Collateral files upload failed")

            # Prepare loan data
            data = {
                'borrower_id': borrower_id,
                'amount': float(amount),
                'status': 'Active',
                'interest_rate': float(interest_rate),
                'duration_days': int(duration_days),
                'due_date': due_date,
                'transaction_costs': float(transaction_costs) if transaction_costs else 0.0,
                'loan_reason': loan_reason if loan_reason else 'Not specified'
            }

            logger.info(f"Inserting loan data for borrower {borrower_id}")
            response = self.supabase.table('loans').insert(data).execute()

            # Check response
            if not hasattr(response, 'data') or not response.data:
                logger.error("Loan insertion failed - no data returned")
                return None

            if len(response.data) == 0 or 'id' not in response.data[0]:
                logger.error("Loan insertion failed - no ID returned")
                return None

            loan_id = response.data[0]['id']
            logger.info(f"Loan created successfully with ID: {loan_id}")

            # Insert file data if we have either contract or collateral files
            if contract_file_url or collateral_file_urls:
                file_data = {
                    'loan_id': loan_id,
                    'docs': [contract_file_url] if contract_file_url else [],
                    'photos': collateral_file_urls if collateral_file_urls else []
                }

                try:
                    logger.info(f"Inserting file data for loan {loan_id}")
                    file_upload_response = self.supabase.table('files').insert(file_data).execute()

                    if hasattr(file_upload_response, 'data') and file_upload_response.data:
                        logger.info("File data inserted successfully")
                    else:
                        logger.warning("File data insertion may have failed")

                except Exception as file_error:
                    logger.error(f"Error inserting file data: {str(file_error)}")
                    # Don't return None here - loan was created successfully

            return loan_id

        except Exception as e:
            logger.error(f"Error creating loan for borrower {borrower_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def upload_contract_file(self, contract_file_obj: Any, borrower_id: Union[int, str]) -> Optional[str]:
        """Uploads the contract file to the Supabase bucket and returns the file URL."""

        if not contract_file_obj or not hasattr(contract_file_obj, 'filename'):
            logger.error("Invalid contract file object")
            return None

        if not contract_file_obj.filename:
            logger.error("Contract file has no filename")
            return None

        try:
            # Get borrower NRC
            nrc_response = (
                self.supabase
                .table('borrowers')
                .select('nrc_number')
                .eq('id', borrower_id)
                .execute()
            )

            if not hasattr(nrc_response, 'data') or not nrc_response.data:
                logger.error(f"Borrower with id {borrower_id} not found for contract upload")
                return None

            nrc_number = nrc_response.data[0].get('nrc_number')
            if not nrc_number:
                logger.error(f"No NRC number found for borrower {borrower_id}")
                return None

            # Construct filename
            file_parts = contract_file_obj.filename.split('.')
            file_extension = file_parts[-1] if len(file_parts) > 1 else 'pdf'
            filename = f"loan_contract/nrc_{nrc_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_extension}"

            # Read file content
            file_bytes = contract_file_obj.read()
            if not file_bytes:
                logger.error("Contract file is empty")
                return None

            # Reset file pointer for potential re-reading
            if hasattr(contract_file_obj, 'seek'):
                contract_file_obj.seek(0)

            # Upload the file
            content_type = getattr(contract_file_obj, 'content_type', 'application/octet-stream')

            upload_response = self.supabase.storage.from_('contracts').upload(
                filename,
                file_bytes,
                {"content-type": content_type}
            )

            # Get the public URL
            public_url = self.supabase.storage.from_('contracts').get_public_url(filename)

            if public_url:
                logger.info(f"Contract file uploaded successfully: {filename}")
                return public_url
            else:
                logger.error("Failed to get public URL for contract file")
                return None

        except Exception as e:
            logger.error(f"Error uploading contract file: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def upload_collateral_files_list(self, collateral_files_list: List[Any], borrower_id: Union[int, str]) -> List[str]:
        """Uploads collateral files to the Supabase bucket and returns list of file URLs."""

        if not collateral_files_list:
            logger.info("No collateral files provided")
            return []

        try:
            # Get borrower NRC
            nrc_response = (
                self.supabase
                .table('borrowers')
                .select('nrc_number')
                .eq('id', borrower_id)
                .execute()
            )

            if not hasattr(nrc_response, 'data') or not nrc_response.data:
                logger.error(f"Borrower with id {borrower_id} not found for collateral upload")
                return []

            nrc_number = nrc_response.data[0].get('nrc_number')
            if not nrc_number:
                logger.error(f"No NRC number found for borrower {borrower_id}")
                return []

            uploaded_urls = []
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            # Upload each collateral file
            for index, file_obj in enumerate(collateral_files_list):
                try:
                    # Skip invalid files
                    if not file_obj or not hasattr(file_obj, 'filename') or not file_obj.filename:
                        logger.warning(f"Skipping invalid collateral file at index {index}")
                        continue

                    # Construct filename
                    file_parts = file_obj.filename.split('.')
                    file_extension = file_parts[-1] if len(file_parts) > 1 else 'jpg'
                    filename = f"collateral/nrc_{nrc_number}_collateral_{index + 1}_{timestamp}.{file_extension}"

                    # Read file content
                    file_bytes = file_obj.read()
                    if not file_bytes:
                        logger.warning(f"Collateral file at index {index} is empty, skipping")
                        continue

                    # Reset file pointer for potential re-reading
                    if hasattr(file_obj, 'seek'):
                        file_obj.seek(0)

                    logger.info(f"Uploading collateral file: {filename}")

                    content_type = getattr(file_obj, 'content_type', 'application/octet-stream')

                    upload_response = self.supabase.storage.from_('collaterals').upload(
                        filename,
                        file_bytes,
                        {"content-type": content_type}
                    )

                    # Get the public URL
                    public_url = self.supabase.storage.from_('collaterals').get_public_url(filename)

                    if public_url:
                        uploaded_urls.append(public_url)
                        logger.info(f"Collateral file uploaded successfully: {filename}")
                    else:
                        logger.error(f"Failed to get public URL for collateral file: {filename}")

                except Exception as file_error:
                    logger.error(f"Error uploading collateral file at index {index}: {str(file_error)}")
                    continue

            logger.info(
                f"Successfully uploaded {len(uploaded_urls)} out of {len(collateral_files_list)} collateral files")
            return uploaded_urls

        except Exception as e:
            logger.error(f"Error uploading collateral files: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def update_overdue_loans(self) -> int:
        """Updates overdue loans and returns the count of updated loans"""

        try:
            now = datetime.now(timezone.utc)
            logger.info("Starting overdue loans update process")

            # Get active loans
            response = (
                self.supabase
                .table('loans')
                .select('id, due_date')
                .eq('status', 'Active')
                .execute()
            )

            # Handle empty table or no response
            if not hasattr(response, 'data') or response.data is None:
                logger.info("No loans data returned from database")
                return 0

            loans = response.data

            if not loans or len(loans) == 0:
                logger.info("No active loans found in database")
                return 0

            logger.info(f"Found {len(loans)} active loans to check")

            overdue_ids = []
            invalid_dates_count = 0

            for loan in loans:
                loan_id = loan.get('id')
                due_date_str = loan.get('due_date')

                if not loan_id:
                    logger.warning("Loan found without ID, skipping")
                    continue

                if not due_date_str:
                    logger.warning(f"Loan {loan_id} has no due_date, skipping")
                    continue

                try:
                    # Parse due date
                    due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))

                    # If due_date is naive, make it UTC-aware by assuming UTC
                    if due_date.tzinfo is None:
                        due_date = due_date.replace(tzinfo=timezone.utc)

                    # Check if overdue
                    if due_date < now:
                        overdue_ids.append(loan_id)
                        logger.debug(f"Loan {loan_id} is overdue (due: {due_date})")

                except ValueError as date_error:
                    invalid_dates_count += 1
                    logger.warning(f"Invalid due_date format for loan {loan_id}: {due_date_str} - {str(date_error)}")
                    continue

            if invalid_dates_count > 0:
                logger.warning(f"Found {invalid_dates_count} loans with invalid due dates")

            # Update overdue loans
            if overdue_ids:
                logger.info(f"Updating {len(overdue_ids)} loans to Overdue status")

                update_response = (
                    self.supabase
                    .table('loans')
                    .update({'status': 'Overdue'})
                    .in_('id', overdue_ids)
                    .execute()
                )

                # Check if update was successful
                if hasattr(update_response, 'data') and update_response.data is not None:
                    updated_count = len(update_response.data) if update_response.data else len(overdue_ids)
                    logger.info(f"Successfully updated {updated_count} loans to overdue status")
                    return updated_count
                else:
                    logger.error("Update response indicates failure")
                    return 0
            else:
                logger.info("No overdue loans found")
                return 0

        except Exception as e:
            logger.error(f"Error updating overdue loans: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return 0

    def get_loans_summary(self) -> Dict[str, Any]:
        """Get a summary of loans statistics - useful for debugging empty tables"""

        try:
            summary = {
                'total_loans': 0,
                'active_loans': 0,
                'overdue_loans': 0,
                'completed_loans': 0,
                'total_borrowers': 0,
                'error': None
            }

            # Get loans count by status
            loans_response = self.supabase.table('loans').select('status').execute()

            if hasattr(loans_response, 'data') and loans_response.data:
                loans_data = loans_response.data
                summary['total_loans'] = len(loans_data)

                for loan in loans_data:
                    status = loan.get('status', 'Unknown')
                    if status == 'Active':
                        summary['active_loans'] += 1
                    elif status == 'Overdue':
                        summary['overdue_loans'] += 1
                    elif status in ['Completed', 'Paid']:
                        summary['completed_loans'] += 1

            # Get borrowers count
            borrowers_response = self.supabase.table('borrowers').select('id').execute()

            if hasattr(borrowers_response, 'data') and borrowers_response.data:
                summary['total_borrowers'] = len(borrowers_response.data)

            logger.info(f"Database summary: {summary}")
            return summary

        except Exception as e:
            error_msg = f"Error getting loans summary: {str(e)}"
            logger.error(error_msg)
            return {
                'total_loans': 0,
                'active_loans': 0,
                'overdue_loans': 0,
                'completed_loans': 0,
                'total_borrowers': 0,
                'error': error_msg
            }