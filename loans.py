from supabase import create_client, Client
from datetime import date, timedelta, datetime, UTC, timezone
from dotenv import load_dotenv
import os
import json
import logging
from typing import Optional, List, Dict, Any, Union
import pandas as pd
import io
from flask import send_file, make_response

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

    def borrower_identity(self, borrower_id, business_id) -> Dict[str, str]:
        """Returns the name and NRC of that borrower for a specific business"""

        if not borrower_id:
            logger.warning("borrower_identity called with empty borrower_id")
            return {'name': 'Unknown', 'nrc': 'Unknown'}

        if not business_id:
            logger.warning("borrower_identity called with empty business_id")
            return {'name': 'Unknown', 'nrc': 'Unknown'}

        try:
            response = (
                self.supabase
                .table('borrowers')
                .select('name, nrc_number')
                .eq('id', borrower_id)
                .eq('business_id', business_id)
                .execute()
            )

            # Check if response has data attribute
            if not hasattr(response, 'data') or response.data is None:
                logger.warning(
                    f"No data attribute in response for borrower_id: {borrower_id}, business_id: {business_id}")
                return {'name': 'Unknown', 'nrc': 'Unknown'}

            # Handle empty results
            if not response.data or len(response.data) == 0:
                logger.warning(f"No borrower found with id: {borrower_id} for business_id: {business_id}")
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
            logger.error(f"Error fetching borrower identity for id {borrower_id}, business_id {business_id}: {str(e)}")
            return {'name': 'Unknown', 'nrc': 'Unknown'}

    def old_borrower_loan(self, borrower_id, business_id, amount: float,
                          transaction_costs: float,
                          interest_rate: float, duration_days: int, due_date: str,
                          contract_file_obj: Optional[Any] = None,
                          collateral_files_list: Optional[List[Any]] = None,
                          loan_reason: Optional[str] = None) -> Optional[int]:
        """Registers a loan for an already existing borrower in the database for a specific business."""

        print(f"=== old_borrower_loan METHOD DEBUG ===")
        print(f"Received parameters:")
        print(f"  borrower_id: {borrower_id} (type: {type(borrower_id)})")
        print(f"  business_id: {business_id} (type: {type(business_id)})")
        print(f"  amount: {amount} (type: {type(amount)})")
        print(f"  transaction_costs: {transaction_costs} (type: {type(transaction_costs)})")
        print(f"  interest_rate: {interest_rate} (type: {type(interest_rate)})")
        print(f"  duration_days: {duration_days} (type: {type(duration_days)})")
        print(f"  due_date: {due_date} (type: {type(due_date)})")
        print(f"  loan_reason: {loan_reason}")
        print(f"  contract_file_obj: {contract_file_obj}")
        print(f"  collateral_files_list: {collateral_files_list}")

        # Input validation with detailed logging
        print("=== INPUT VALIDATION ===")

        if not borrower_id:
            print("VALIDATION FAILED: borrower_id is required")
            logger.error("borrower_id is required")
            return None
        print(f"✓ borrower_id validation passed: {borrower_id}")

        if not business_id:
            print("VALIDATION FAILED: business_id is required")
            logger.error("business_id is required")
            return None
        print(f"✓ business_id validation passed: {business_id}")

        if not isinstance(amount, (int, float)) or amount <= 0:
            print(f"VALIDATION FAILED: Invalid amount: {amount} (type: {type(amount)})")
            logger.error(f"Invalid amount: {amount}")
            return None
        print(f"✓ amount validation passed: {amount}")

        if not isinstance(interest_rate, (int, float)) or interest_rate < 0:
            print(f"VALIDATION FAILED: Invalid interest_rate: {interest_rate} (type: {type(interest_rate)})")
            logger.error(f"Invalid interest_rate: {interest_rate}")
            return None
        print(f"✓ interest_rate validation passed: {interest_rate}")

        if not isinstance(duration_days, int) or duration_days <= 0:
            print(f"VALIDATION FAILED: Invalid duration_days: {duration_days} (type: {type(duration_days)})")
            logger.error(f"Invalid duration_days: {duration_days}")
            return None
        print(f"✓ duration_days validation passed: {duration_days}")

        print("All input validations passed!")

        # Verify borrower exists for this business
        print("=== BORROWER VERIFICATION ===")
        try:
            borrower_check = self.borrower_identity(borrower_id, business_id)
            print(f"Borrower check result: {borrower_check}")

            if borrower_check['name'] == 'Unknown':
                print(
                    f"BORROWER VERIFICATION FAILED: Borrower with id {borrower_id} does not exist for business_id {business_id}")
                logger.error(f"Borrower with id {borrower_id} does not exist for business_id {business_id}")
                return None
            print(f"✓ Borrower verification passed: {borrower_check['name']}")
        except Exception as borrower_error:
            print(f"BORROWER VERIFICATION ERROR: {borrower_error}")
            logger.error(f"Error verifying borrower: {borrower_error}")
            return None

        contract_file_url = None
        collateral_file_urls = []

        try:
            # Upload contract file if provided
            print("=== FILE UPLOAD SECTION ===")
            if contract_file_obj:
                print(f"Uploading contract file: {getattr(contract_file_obj, 'filename', 'unknown')}")
                try:
                    contract_file_url = self.upload_contract_file(contract_file_obj, borrower_id)
                    if contract_file_url:
                        print(f"✓ Contract file uploaded successfully: {contract_file_url}")
                        logger.info(f"Contract file uploaded: {contract_file_url}")
                    else:
                        print("⚠ Contract file upload failed")
                        logger.warning("Contract file upload failed")
                except Exception as contract_error:
                    print(f"CONTRACT UPLOAD ERROR: {contract_error}")
                    logger.error(f"Contract upload error: {contract_error}")
                    # Don't return None here - continue with loan creation
            else:
                print("No contract file provided")

            # Upload collateral files if provided
            if collateral_files_list and len(collateral_files_list) > 0:
                print(f"Uploading {len(collateral_files_list)} collateral files")
                try:
                    collateral_file_urls = self.upload_collateral_files_list(collateral_files_list, borrower_id)
                    if collateral_file_urls:
                        print(f"✓ Collateral files uploaded successfully: {len(collateral_file_urls)} files")
                        logger.info(f"Collateral files uploaded: {len(collateral_file_urls)} files")
                    else:
                        print("⚠ Collateral files upload failed")
                        logger.warning("Collateral files upload failed")
                except Exception as collateral_error:
                    print(f"COLLATERAL UPLOAD ERROR: {collateral_error}")
                    logger.error(f"Collateral upload error: {collateral_error}")
                    # Don't return None here - continue with loan creation
            else:
                print("No collateral files provided")

            # Prepare loan data
            print("=== PREPARING LOAN DATA ===")
            data = {
                'borrower_id': borrower_id,
                'business_id': business_id,
                'amount': float(amount),
                'status': 'Active',
                'interest_rate': float(interest_rate),
                'duration_days': int(duration_days),
                'due_date': due_date,
                'transaction_costs': float(transaction_costs) if transaction_costs else 0.0,
                'loan_reason': loan_reason if loan_reason else 'Not specified'
            }

            print(f"Loan data prepared: {data}")

            # Insert loan data
            print("=== DATABASE INSERTION ===")
            logger.info(f"Inserting loan data for borrower {borrower_id} in business {business_id}")

            try:
                response = self.supabase.table('loans').insert(data).execute()
                print(f"Database response: {response}")
                print(f"Response has data attribute: {hasattr(response, 'data')}")
                if hasattr(response, 'data'):
                    print(f"Response data: {response.data}")
                    print(f"Response data type: {type(response.data)}")
                    print(f"Response data length: {len(response.data) if response.data else 'None'}")
            except Exception as db_error:
                print(f"DATABASE INSERTION ERROR: {db_error}")
                logger.error(f"Database insertion error: {db_error}")
                return None

            # Check response
            if not hasattr(response, 'data') or not response.data:
                print("LOAN INSERTION FAILED: No data returned from database")
                logger.error("Loan insertion failed - no data returned")
                return None

            if len(response.data) == 0 or 'id' not in response.data[0]:
                print("LOAN INSERTION FAILED: No ID returned from database")
                print(f"Response data content: {response.data}")
                logger.error("Loan insertion failed - no ID returned")
                return None

            loan_id = response.data[0]['id']
            print(f"✓ LOAN CREATED SUCCESSFULLY with ID: {loan_id}")
            logger.info(f"Loan created successfully with ID: {loan_id}")

            # Insert file data if we have either contract or collateral files
            if contract_file_url or collateral_file_urls:
                print("=== INSERTING FILE DATA ===")
                file_data = {
                    'loan_id': loan_id,
                    'business_id': business_id,
                    'docs': [contract_file_url] if contract_file_url else [],
                    'photos': collateral_file_urls if collateral_file_urls else []
                }

                try:
                    print(f"File data to insert: {file_data}")
                    logger.info(f"Inserting file data for loan {loan_id}")
                    file_upload_response = self.supabase.table('files').insert(file_data).execute()

                    if hasattr(file_upload_response, 'data') and file_upload_response.data:
                        print("✓ File data inserted successfully")
                        logger.info("File data inserted successfully")
                    else:
                        print("⚠ File data insertion may have failed")
                        logger.warning("File data insertion may have failed")

                except Exception as file_error:
                    print(f"FILE DATA INSERTION ERROR: {file_error}")
                    logger.error(f"Error inserting file data: {str(file_error)}")
                    # Don't return None here - loan was created successfully

            print(f"=== FINAL RESULT: RETURNING LOAN_ID {loan_id} ===")
            return loan_id

        except Exception as e:
            print(f"CRITICAL ERROR in old_borrower_loan: {e}")
            logger.error(f"Error creating loan for borrower {borrower_id} in business {business_id}: {str(e)}")
            import traceback
            print(f"Full traceback: {traceback.format_exc()}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def upload_contract_file(self, contract_file_obj: Any, borrower_id,
                             business_id) -> Optional[str]:
        """Uploads the contract file to the Supabase bucket and returns the file URL for a specific business."""

        if not contract_file_obj or not hasattr(contract_file_obj, 'filename'):
            logger.error("Invalid contract file object")
            return None

        if not contract_file_obj.filename:
            logger.error("Contract file has no filename")
            return None

        if not business_id:
            logger.error("business_id is required for contract file upload")
            return None

        try:
            # Get borrower NRC for the specific business
            nrc_response = (
                self.supabase
                .table('borrowers')
                .select('nrc_number')
                .eq('id', borrower_id)
                .eq('business_id', business_id)
                .execute()
            )

            if not hasattr(nrc_response, 'data') or not nrc_response.data:
                logger.error(f"Borrower with id {borrower_id} not found for business {business_id} for contract upload")
                return None

            nrc_number = nrc_response.data[0].get('nrc_number')
            if not nrc_number:
                logger.error(f"No NRC number found for borrower {borrower_id} in business {business_id}")
                return None

            # Construct filename with business_id for better organization
            file_parts = contract_file_obj.filename.split('.')
            file_extension = file_parts[-1] if len(file_parts) > 1 else 'pdf'
            filename = f"loan_contract/business_{business_id}/nrc_{nrc_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_extension}"

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
                logger.info(f"Contract file uploaded successfully for business {business_id}: {filename}")
                return public_url
            else:
                logger.error("Failed to get public URL for contract file")
                return None

        except Exception as e:
            logger.error(
                f"Error uploading contract file for borrower {borrower_id} in business {business_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def upload_collateral_files_list(self, collateral_files_list: List[Any], borrower_id,
                                     business_id) -> List[str]:
        """Uploads collateral files to the Supabase bucket and returns list of file URLs for a specific business."""

        if not collateral_files_list:
            logger.info("No collateral files provided")
            return []

        if not business_id:
            logger.error("business_id is required for collateral files upload")
            return []

        try:
            # Get borrower NRC for the specific business
            nrc_response = (
                self.supabase
                .table('borrowers')
                .select('nrc_number')
                .eq('id', borrower_id)
                .eq('business_id', business_id)
                .execute()
            )

            if not hasattr(nrc_response, 'data') or not nrc_response.data:
                logger.error(
                    f"Borrower with id {borrower_id} not found for business {business_id} for collateral upload")
                return []

            nrc_number = nrc_response.data[0].get('nrc_number')
            if not nrc_number:
                logger.error(f"No NRC number found for borrower {borrower_id} in business {business_id}")
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

                    # Construct filename with business_id for better organization
                    file_parts = file_obj.filename.split('.')
                    file_extension = file_parts[-1] if len(file_parts) > 1 else 'jpg'
                    filename = f"collateral/business_{business_id}/nrc_{nrc_number}_collateral_{index + 1}_{timestamp}.{file_extension}"

                    # Read file content
                    file_bytes = file_obj.read()
                    if not file_bytes:
                        logger.warning(f"Collateral file at index {index} is empty, skipping")
                        continue

                    # Reset file pointer for potential re-reading
                    if hasattr(file_obj, 'seek'):
                        file_obj.seek(0)

                    logger.info(f"Uploading collateral file for business {business_id}: {filename}")

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
                    logger.error(
                        f"Error uploading collateral file at index {index} for business {business_id}: {str(file_error)}")
                    continue

            logger.info(
                f"Successfully uploaded {len(uploaded_urls)} out of {len(collateral_files_list)} collateral files for business {business_id}")
            return uploaded_urls

        except Exception as e:
            logger.error(
                f"Error uploading collateral files for borrower {borrower_id} in business {business_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def update_overdue_loans(self, business_id) -> int:
        """Updates overdue loans for a specific business and returns the count of updated loans"""

        if not business_id:
            logger.error("business_id is required for updating overdue loans")
            return 0

        try:
            now = datetime.now(timezone.utc)
            logger.info(f"Starting overdue loans update process for business {business_id}")

            # Get active loans for the specific business
            response = (
                self.supabase
                .table('loans')
                .select('id, due_date')
                .eq('status', 'Active')
                .eq('business_id', business_id)
                .execute()
            )

            # Handle empty table or no response
            if not hasattr(response, 'data') or response.data is None:
                logger.info(f"No loans data returned from database for business {business_id}")
                return 0

            loans = response.data

            if not loans or len(loans) == 0:
                logger.info(f"No active loans found in database for business {business_id}")
                return 0

            logger.info(f"Found {len(loans)} active loans to check for business {business_id}")

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
                        logger.debug(f"Loan {loan_id} is overdue (due: {due_date}) for business {business_id}")

                except ValueError as date_error:
                    invalid_dates_count += 1
                    logger.warning(
                        f"Invalid due_date format for loan {loan_id} in business {business_id}: {due_date_str} - {str(date_error)}")
                    continue

            if invalid_dates_count > 0:
                logger.warning(f"Found {invalid_dates_count} loans with invalid due dates for business {business_id}")

            # Update overdue loans
            if overdue_ids:
                logger.info(f"Updating {len(overdue_ids)} loans to Overdue status for business {business_id}")

                update_response = (
                    self.supabase
                    .table('loans')
                    .update({'status': 'Overdue'})
                    .in_('id', overdue_ids)
                    .eq('business_id', business_id)
                    .execute()
                )

                # Check if update was successful
                if hasattr(update_response, 'data') and update_response.data is not None:
                    updated_count = len(update_response.data) if update_response.data else len(overdue_ids)
                    logger.info(
                        f"Successfully updated {updated_count} loans to overdue status for business {business_id}")
                    return updated_count
                else:
                    logger.error(f"Update response indicates failure for business {business_id}")
                    return 0
            else:
                logger.info(f"No overdue loans found for business {business_id}")
                return 0

        except Exception as e:
            logger.error(f"Error updating overdue loans for business {business_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return 0

    def get_loans_summary(self, business_id) -> Dict[str, Any]:
        """Get a summary of loans statistics for a specific business - useful for debugging empty tables"""

        if not business_id:
            return {
                'total_loans': 0,
                'active_loans': 0,
                'overdue_loans': 0,
                'completed_loans': 0,
                'total_borrowers': 0,
                'error': 'business_id is required for loans summary'
            }

        try:
            summary = {
                'business_id': business_id,
                'total_loans': 0,
                'active_loans': 0,
                'overdue_loans': 0,
                'completed_loans': 0,
                'total_borrowers': 0,
                'error': None
            }

            # Get loans count by status for the specific business
            loans_response = (
                self.supabase
                .table('loans')
                .select('status')
                .eq('business_id', business_id)
                .execute()
            )

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

            # Get borrowers count for the specific business
            borrowers_response = (
                self.supabase
                .table('borrowers')
                .select('id')
                .eq('business_id', business_id)
                .execute()
            )

            if hasattr(borrowers_response, 'data') and borrowers_response.data:
                summary['total_borrowers'] = len(borrowers_response.data)

            logger.info(f"Database summary for business {business_id}: {summary}")
            return summary

        except Exception as e:
            error_msg = f"Error getting loans summary for business {business_id}: {str(e)}"
            logger.error(error_msg)
            return {
                'business_id': business_id,
                'total_loans': 0,
                'active_loans': 0,
                'overdue_loans': 0,
                'completed_loans': 0,
                'total_borrowers': 0,
                'error': error_msg
            }

    def filtered_loans(self, business_id, from_date=None, to_date=None, loan_type='All Loans'):
        """Returns loan information according to the filters for a specific business"""

        if not business_id:
            logger.error("business_id is required for filtered loans")
            return []

        try:
            # Build the base query with business_id filter
            query = (
                self.supabase
                .table('loans')
                .select('id', 'borrower_id', 'amount', 'status', 'created_at', 'due_date')
                .eq('business_id', business_id)
            )

            # Apply date filters if provided
            if from_date:
                query = query.gte('created_at', from_date)
            if to_date:
                query = query.lte('created_at', to_date)

            # Apply loan type filter using the status column directly
            if loan_type.lower() in ['overdue loans', 'overdue']:
                query = query.eq('status', 'Overdue')
                logger.debug(f"Filtering for Overdue loans in business {business_id}")
            elif loan_type.lower() in ['active loans', 'active']:
                query = query.eq('status', 'Active')
                logger.debug(f"Filtering for Active loans in business {business_id}")
            else:
                logger.debug(f"No status filter applied for business {business_id}, loan_type = {loan_type}")

            # Execute the query with ordering
            response = query.order('id', desc=True).execute()
            logger.debug(
                f"Query returned {len(response.data) if response.data else 0} loans for business {business_id}")

            if not response.data or len(response.data) == 0:
                return []

            filtered_loans = []
            for loan in response.data:
                try:
                    # Step 1: Get borrower name and NRC number for the specific business
                    borrower_info = (
                        self.supabase
                        .table('borrowers')
                        .select('name', 'nrc_number')
                        .eq('id', loan['borrower_id'])
                        .eq('business_id', business_id)
                        .execute()
                    ).data

                    if borrower_info:
                        borrower_name = borrower_info[0]['name']
                        nrc_number = borrower_info[0]['nrc_number']
                    else:
                        borrower_name = "Unknown"
                        nrc_number = "N/A"

                    # Step 2: Get files for the loan in the specific business
                    file_info = (
                        self.supabase
                        .table('files')
                        .select('docs', 'photos')
                        .eq('loan_id', loan['id'])
                        .eq('business_id', business_id)
                        .limit(1)
                        .execute()
                    ).data
                    file_data = file_info[0] if file_info else {}

                    # Extract the first contract URL from the docs array
                    docs_array = file_data.get('docs', [])
                    contract = docs_array[0] if docs_array and len(docs_array) > 0 else None

                    collateral_photos = file_data.get('photos', []) if isinstance(file_data.get('photos'), list) else []

                    filtered_loans.append({
                        'name': borrower_name,
                        'nrc_number': nrc_number,
                        'amount': f"ZMK {loan['amount']:,.2f}",
                        'status': loan['status'],  # Use the actual status from the database
                        'issue_date': loan['created_at'],
                        'due_date': loan['due_date'],
                        'contract': contract,
                        'collateral_photos': collateral_photos
                    })
                except Exception as e:
                    logger.error(f"Error processing loan data for business {business_id}: {e}")
                    continue

            logger.info(f"Returned {len(filtered_loans)} filtered loans for business {business_id}")
            return filtered_loans

        except Exception as e:
            logger.error(f"Error getting filtered loans for business {business_id}: {e}")
            return []

    def search_by_id(self, business_id, search_query):
        """Search loans by borrower name (title case) or NRC number for a specific business"""

        if not business_id:
            logger.error("business_id is required for search")
            return []

        try:
            if not search_query or search_query.strip() == "":
                return []

            search_query = search_query.strip()
            logger.info(f"🔍 Searching for: '{search_query}' in business {business_id}")

            # Search by name (case-insensitive partial match) for the specific business
            name_results = (
                self.supabase
                .table('borrowers')
                .select('id', 'name', 'nrc_number')
                .filter('name', 'ilike', f'%{search_query}%')
                .eq('business_id', business_id)
                .execute()
            )
            logger.debug(f"👤 Name results for business {business_id}: {name_results.data}")

            # Search by NRC number (case-insensitive partial match) for the specific business
            nrc_results = (
                self.supabase
                .table('borrowers')
                .select('id', 'name', 'nrc_number')
                .filter('nrc_number', 'ilike', f'%{search_query}%')
                .eq('business_id', business_id)
                .execute()
            )
            logger.debug(f"🆔 NRC results for business {business_id}: {nrc_results.data}")

            # Combine results and remove duplicates
            all_borrowers = []
            seen_ids = set()

            for result_set in [name_results.data, nrc_results.data]:
                for borrower in result_set:
                    if borrower['id'] not in seen_ids:
                        all_borrowers.append(borrower)
                        seen_ids.add(borrower['id'])

            logger.debug(f"👥 All borrowers found for business {business_id}: {all_borrowers}")

            if not all_borrowers:
                logger.info(f"❌ No borrowers found for business {business_id}!")
                return []

            # Get borrower IDs for loan lookup
            borrower_ids = [borrower['id'] for borrower in all_borrowers]
            logger.debug(f"🔢 Borrower IDs for business {business_id}: {borrower_ids}")

            # Get all loans for these borrowers in the specific business
            loans_response = (
                self.supabase
                .table('loans')
                .select('id', 'borrower_id', 'amount', 'status', 'created_at', 'due_date')
                .in_('borrower_id', borrower_ids)
                .eq('business_id', business_id)
                .order('id', desc=True)
                .execute()
            )

            logger.debug(f"💰 Loans response for business {business_id}: {loans_response.data}")

            if not loans_response.data:
                logger.info(f"❌ No loans found for these borrowers in business {business_id}!")
                return []

            # Create a mapping of borrower_id to borrower info for quick lookup
            borrower_map = {borrower['id']: borrower for borrower in all_borrowers}
            logger.debug(f"🗺️ Borrower map for business {business_id}: {borrower_map}")

            search_results = []
            for loan in loans_response.data:
                try:
                    logger.debug(f"🔄 Processing loan for business {business_id}: {loan}")

                    # Get borrower info from our mapping
                    borrower_info = borrower_map.get(loan['borrower_id'])

                    if borrower_info:
                        borrower_name = borrower_info['name']
                        nrc_number = borrower_info['nrc_number']
                    else:
                        borrower_name = "Unknown"
                        nrc_number = "N/A"

                    logger.debug(f"👤 Borrower info for business {business_id}: {borrower_name}, {nrc_number}")

                    # Get files for the loan in the specific business
                    file_info = (
                        self.supabase
                        .table('files')
                        .select('docs', 'photos')
                        .eq('loan_id', loan['id'])
                        .eq('business_id', business_id)
                        .limit(1)
                        .execute()
                    ).data

                    logger.debug(f"📁 File info for business {business_id}: {file_info}")

                    file_data = file_info[0] if file_info else {}

                    # Extract the first contract URL from the docs array
                    docs_array = file_data.get('docs', [])
                    contract = docs_array[0] if docs_array and len(docs_array) > 0 else None

                    collateral_photos = file_data.get('photos', []) if isinstance(file_data.get('photos'), list) else []

                    # Determine loan status based on due date
                    from datetime import datetime
                    current_date = datetime.now()
                    due_date = datetime.fromisoformat(loan['due_date'].replace('Z', '+00:00')) if loan[
                        'due_date'] else None

                    if due_date and due_date < current_date:
                        computed_status = 'Overdue'
                    else:
                        computed_status = 'Active'

                    result_item = {
                        'name': borrower_name,
                        'nrc_number': nrc_number,
                        'amount': f"ZMK {loan['amount']:,.2f}",
                        'status': loan['status'],
                        'computed_status': computed_status,
                        'issue_date': loan['created_at'],
                        'due_date': loan['due_date'],
                        'contract': contract,
                        'collateral_photos': collateral_photos
                    }

                    logger.debug(f"✅ Added result for business {business_id}: {result_item}")
                    search_results.append(result_item)

                except Exception as e:
                    logger.error(f"❌ Error processing search result for business {business_id}: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    continue

            logger.info(f"📊 Final search results for business {business_id}: {len(search_results)} items found")
            return search_results

        except Exception as e:
            logger.error(f"❌ Error searching loans for business {business_id}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def create_csv_loans(self, business_id, start_date, end_date):
        """Exports the loans as a CSV string for a specific business."""

        if not business_id:
            logger.error("business_id is required for CSV export")
            return None

        try:
            loans_response = (
                self.supabase
                .table('loans')
                .select('*')
                .gte('created_at', start_date)
                .lte('created_at', end_date)
                .eq('business_id', business_id)
                .execute()
            )

            if not loans_response.data:
                logger.info(f"No loans found for business {business_id} between {start_date} and {end_date}")
                return pd.DataFrame().to_csv(index=False)  # Return empty CSV

            loans_df = pd.DataFrame(loans_response.data)
            loans_csv = loans_df.to_csv(index=False)

            logger.info(f"CSV export completed for business {business_id}: {len(loans_response.data)} loans exported")
            return loans_csv

        except Exception as e:
            logger.error(f'Exception creating CSV for business {business_id}: {e}')
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def download_csv(self, business_id, start_date, end_date):
        """Returns a Flask CSV download response of capital transactions for a specific business."""

        if not business_id:
            logger.error("business_id is required for CSV download")
            return make_response("Error: business_id is required", 400)

        try:
            csv_file = self.create_csv_loans(business_id, start_date, end_date)
            if not csv_file:
                raise ValueError("No CSV file was generated.")

            csv_buffer = io.BytesIO()
            csv_buffer.write(csv_file.encode('utf-8'))
            csv_buffer.seek(0)

            filename = f"capital_transactions_business_{business_id}_{start_date}_to_{end_date}.csv"

            logger.info(f"CSV download initiated for business {business_id} from {start_date} to {end_date}")

            return send_file(
                csv_buffer,
                mimetype='text/csv',
                as_attachment=True,
                download_name=filename
            )

        except Exception as e:
            logger.error(f"ERROR in download_csv for business {business_id}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return make_response(f"Error generating CSV for business {business_id}: {e}", 500)

