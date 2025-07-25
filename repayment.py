from supabase import create_client, Client
import datetime
import os
import logging
from typing import Optional, List, Dict, Any, Union
from decimal import Decimal, InvalidOperation
from dotenv import load_dotenv

# Import your registration module - assuming it exists
try:
    from registration import Registration
except ImportError:
    logging.warning("Registration module not found. Some functionality may be limited.")
    Registration = None

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RepaymentError(Exception):
    """Custom exception for Repayment class errors"""
    pass


class Repayment:
    def __init__(self):
        try:
            # Load environment variables
            load_dotenv()

            url = os.getenv("SUPABASE_URL")
            service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

            if not url or not service_role_key:
                raise RepaymentError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set in environment variables.")

            self.supabase: Client = create_client(url, service_role_key)

            # Test connection
            self._test_connection()

            # Initialize registration tool if available
            if Registration:
                try:
                    self.reg_tool = Registration()
                    logger.info("Registration tool initialized successfully")
                except Exception as e:
                    logger.warning(f"Failed to initialize Registration tool: {str(e)}")
                    self.reg_tool = None
            else:
                self.reg_tool = None
                logger.warning("Registration module not available")

        except Exception as e:
            logger.error(f"Failed to initialize Repayment class: {str(e)}")
            raise RepaymentError(f"Initialization failed: {str(e)}")

    def _test_connection(self) -> None:
        """Test the Supabase connection"""
        try:
            # Simple query to test connection
            response = self.supabase.table('loans').select('id').limit(1).execute()
            logger.info("Supabase connection established successfully")
        except Exception as e:
            logger.error(f"Supabase connection test failed: {str(e)}")
            raise RepaymentError(f"Database connection failed: {str(e)}")

    def show_loans(self, nrc, business_id) -> List[Dict[str, Any]]:
        """Returns a list of active, default and overdue loans for that borrower under a specific business using the NRC."""

        if not nrc or not isinstance(nrc, str):
            logger.error("Invalid NRC provided")
            return []

        if not business_id or not isinstance(business_id, str):
            logger.error("Invalid business_id provided")
            return []

        if not self.reg_tool:
            logger.error("Registration tool not available - cannot fetch borrower by NRC")
            return []

        try:
            # Get the borrower_id
            logger.info(f"Fetching borrower data for NRC: {nrc}")
            borrower_data = self.reg_tool.get_borrower_id(nrc, business_id=business_id)

            if not borrower_data or not isinstance(borrower_data, dict):
                logger.warning(f"No borrower found for NRC: {nrc} under business: {business_id}")
                return []

            borrower_id = borrower_data.get('id')
            if not borrower_id:
                logger.warning(f"No borrower ID found for NRC: {nrc}")
                return []

            logger.info(f"Found borrower ID: {borrower_id} for NRC: {nrc} under business: {business_id}")
            loans = self.get_loans(borrower_id, business_id=business_id)

            logger.info(f"Found {len(loans)} loans for borrower {borrower_id} under business: {business_id}")
            return loans

        except Exception as e:
            logger.error(f"Error fetching loans for NRC {nrc} under business {business_id}: {str(e)}")
            return []

    def get_loans(self, borrower_id, business_id) -> List[Dict[str, Any]]:
        """Returns a list of active, default, and overdue loans for a specific borrower and business."""

        if not borrower_id:
            logger.error("borrower_id is required")
            return []

        if not business_id:
            logger.error("business_id is required")
            return []

        try:
            logger.info(f"Fetching loans for borrower ID: {borrower_id} under business: {business_id}")

            loans_response = (
                self.supabase
                .table('loans')
                .select('*')
                .eq('borrower_id', borrower_id)
                .eq('business_id', business_id)
                .in_('status', ['Overdue', 'Default', 'Active'])
                .execute()
            )

            if not hasattr(loans_response, 'data') or loans_response.data is None:
                logger.info(f"No loans data returned for borrower {borrower_id} under business {business_id}")
                return []

            loans = loans_response.data

            if not loans:
                logger.info(
                    f"No active/overdue/default loans found for borrower {borrower_id} under business {business_id}")
                return []

            valid_loans = []
            for loan in loans:
                if isinstance(loan, dict) and loan.get('id'):
                    valid_loans.append(loan)
                else:
                    logger.warning(f"Invalid loan data structure found: {loan}")

            logger.info(
                f"Returning {len(valid_loans)} valid loans for borrower {borrower_id} under business {business_id}")
            return valid_loans

        except Exception as e:
            logger.error(f"Error fetching loans for borrower {borrower_id} under business {business_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def submit_repayment(self, loan_id, status: str, amount: Union[float, str, int],
                         repayment_date: str, discount: Union[float, str, int] = 0,
                         business_id=None) -> bool:
        """Submits the repayment of a loan and updates the loan status for a specific business."""

        # Input validation
        if not loan_id:
            logger.error("loan_id is required")
            return False

        if not business_id:
            logger.error("business_id is required")
            return False

        if not status or not isinstance(status, str):
            logger.error("Valid status is required")
            return False

        if not repayment_date or not isinstance(repayment_date, str):
            logger.error("Valid repayment_date is required")
            return False

        try:
            amount = float(amount) if amount else 0.0
            if amount < 0:
                logger.error("Amount cannot be negative")
                return False
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid amount provided: {amount} - {str(e)}")
            return False

        try:
            discount = float(discount) if discount else 0.0
            if discount < 0:
                logger.error("Discount cannot be negative")
                return False
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid discount provided: {discount} - {str(e)}")
            return False

        try:
            datetime.datetime.fromisoformat(repayment_date.replace('Z', '+00:00'))
        except ValueError:
            logger.error(f"Invalid repayment_date format: {repayment_date}. Expected ISO format (YYYY-MM-DD)")
            return False

        try:
            logger.info(
                f"Processing repayment for loan {loan_id}: amount={amount}, discount={discount}, status={status}")

            # Step 1: Insert repayment record
            repayment_data = {
                'loan_id': loan_id,
                'amount': amount,
                'repayment_date': repayment_date,
                'discount': discount,
                'business_id': business_id
            }

            logger.info("Inserting repayment record")
            insert_response = self.supabase.table('repayments').insert(repayment_data).execute()

            if not hasattr(insert_response, 'data') or not insert_response.data:
                logger.error("Repayment insertion failed - no data returned")
                return False

            logger.info("Repayment recorded successfully")

            # Step 2: Fetch current loan amount
            logger.info(f"Fetching current loan data for ID: {loan_id} under business: {business_id}")
            loan_response = (
                self.supabase
                .table('loans')
                .select('amount')
                .eq('id', loan_id)
                .eq('business_id', business_id)
                .execute()
            )

            if not hasattr(loan_response, 'data') or not loan_response.data:
                logger.error(f"Loan with ID {loan_id} not found for business {business_id}")
                return False

            current_amount = loan_response.data[0].get('amount')
            if current_amount is None:
                logger.error(f"Loan {loan_id} has no amount field")
                return False

            try:
                current_amount = float(current_amount)
                updated_amount = current_amount - amount - discount
                if updated_amount < 0:
                    logger.info(f"Loan amount would be negative ({updated_amount}), setting to 0")
                    updated_amount = 0
                logger.info(f"Updating loan amount from {current_amount} to {updated_amount}")
            except (ValueError, TypeError) as e:
                logger.error(f"Error calculating updated amount: {str(e)}")
                return False

            # Step 3: Update loan status only
            logger.info(f"Updating loan {loan_id} status to {status}")
            update_response = (
                self.supabase
                .table("loans")
                .update({
                    "status": status
                })
                .eq("id", loan_id)
                .eq("business_id", business_id)
                .execute()
            )

            logger.info("Loan status updated successfully")
            return True

        except Exception as e:
            logger.error(f"Error processing repayment for loan {loan_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def get_loan_by_id(self, loan_id, business_id) -> Optional[Dict[str, Any]]:
        """Returns the full row of the loan specific to that loan ID and business."""

        if not loan_id:
            logger.error("loan_id is required")
            return None

        if not business_id:
            logger.error("business_id is required")
            return None

        try:
            logger.info(f"Fetching loan with ID: {loan_id} under business: {business_id}")

            response = (
                self.supabase
                .table('loans')
                .select('*')
                .eq('id', loan_id)
                .eq('business_id', business_id)
                .execute()
            )

            if not hasattr(response, 'data') or response.data is None:
                logger.warning(f"No loan data returned for ID: {loan_id} under business: {business_id}")
                return None

            if not response.data or len(response.data) == 0:
                logger.warning(f"No loan found with ID: {loan_id} under business: {business_id}")
                return None

            loan_data = response.data[0]
            logger.info(f"Loan data found for ID {loan_id} under business: {business_id}")
            return loan_data

        except Exception as e:
            logger.error(f"Error fetching loan with ID {loan_id} under business {business_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def get_repayments_by_loan_id(self, loan_id, business_id) -> List[Dict[str, Any]]:
        """Returns all repayments for a specific loan and business."""

        if not loan_id:
            logger.error("loan_id is required")
            return []

        if not business_id:
            logger.error("business_id is required")
            return []

        try:
            logger.info(f"Fetching repayments for loan ID: {loan_id} under business: {business_id}")

            response = (
                self.supabase
                .table('repayments')
                .select('*')
                .eq('loan_id', loan_id)
                .eq('business_id', business_id)
                .order('repayment_date', desc=True)
                .execute()
            )

            if not hasattr(response, 'data') or response.data is None:
                logger.info(f"No repayments data returned for loan {loan_id} under business: {business_id}")
                return []

            repayments = response.data

            if not repayments:
                logger.info(f"No repayments found for loan {loan_id} under business: {business_id}")
                return []

            logger.info(f"Found {len(repayments)} repayments for loan {loan_id} under business: {business_id}")
            return repayments

        except Exception as e:
            logger.error(f"Error fetching repayments for loan {loan_id} under business {business_id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

    def get_total_repayments_by_loan_id(self, loan_id, business_id) -> Dict[str, float]:
        """Returns total repayments and discounts for a specific loan and business."""

        if not loan_id:
            logger.error("loan_id is required")
            return {'total_amount': 0.0, 'total_discount': 0.0, 'net_repayment': 0.0}

        if not business_id:
            logger.error("business_id is required")
            return {'total_amount': 0.0, 'total_discount': 0.0, 'net_repayment': 0.0}

        try:
            repayments = self.get_repayments_by_loan_id(loan_id, business_id)

            total_amount = 0.0
            total_discount = 0.0

            for repayment in repayments:
                try:
                    amount = float(repayment.get('amount', 0))
                    discount = float(repayment.get('discount', 0))

                    total_amount += amount
                    total_discount += discount

                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid repayment data in loan {loan_id}: {repayment} - {str(e)}")
                    continue

            net_repayment = total_amount + total_discount

            logger.info(
                f"Loan {loan_id} totals under business {business_id} - "
                f"Amount: {total_amount}, Discount: {total_discount}, Net: {net_repayment}"
            )

            return {
                'total_amount': total_amount,
                'total_discount': total_discount,
                'net_repayment': net_repayment
            }

        except Exception as e:
            logger.error(
                f"Error calculating total repayments for loan {loan_id} under business {business_id}: {str(e)}")
            return {'total_amount': 0.0, 'total_discount': 0.0, 'net_repayment': 0.0}

    def get_repayment_summary(self, business_id) -> Dict[str, Any]:
        """Get a summary of repayments statistics for a specific business."""

        if not business_id:
            logger.error("business_id is required")
            return {
                'total_repayments': 0,
                'total_amount_repaid': 0.0,
                'total_discounts': 0.0,
                'loans_with_repayments': 0,
                'error': 'Missing business_id'
            }

        try:
            summary = {
                'total_repayments': 0,
                'total_amount_repaid': 0.0,
                'total_discounts': 0.0,
                'loans_with_repayments': 0,
                'error': None
            }

            # Get all repayments for the specific business
            repayments_response = (
                self.supabase
                .table('repayments')
                .select('*')
                .eq('business_id', business_id)
                .execute()
            )

            if hasattr(repayments_response, 'data') and repayments_response.data:
                repayments_data = repayments_response.data
                summary['total_repayments'] = len(repayments_data)

                unique_loan_ids = set()

                for repayment in repayments_data:
                    try:
                        amount = float(repayment.get('amount', 0))
                        discount = float(repayment.get('discount', 0))
                        loan_id = repayment.get('loan_id')

                        summary['total_amount_repaid'] += amount
                        summary['total_discounts'] += discount

                        if loan_id:
                            unique_loan_ids.add(loan_id)

                    except (ValueError, TypeError) as e:
                        logger.warning(f"Invalid repayment data: {repayment} - {str(e)}")
                        continue

                summary['loans_with_repayments'] = len(unique_loan_ids)

            logger.info(f"Repayments summary for business {business_id}: {summary}")
            return summary

        except Exception as e:
            error_msg = f"Error getting repayments summary for business {business_id}: {str(e)}"
            logger.error(error_msg)
            return {
                'total_repayments': 0,
                'total_amount_repaid': 0.0,
                'total_discounts': 0.0,
                'loans_with_repayments': 0,
                'error': error_msg
            }

    def validate_repayment_data(self, loan_id: Union[int, str], amount: Union[float, str, int],
                                repayment_date: str, business_id) -> Dict[str, Any]:
        """Validates repayment data before processing, scoped to a specific business"""

        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'loan_data': None
        }

        # Fetch loan with business context
        loan_data = self.get_loan_by_id(loan_id, business_id)

        if not loan_data:
            validation_result['is_valid'] = False
            validation_result['errors'].append(f"Loan with ID {loan_id} not found")
            return validation_result

        # Check if loan belongs to the business
        if str(loan_data.get('business_id')) != str(business_id):
            validation_result['is_valid'] = False
            validation_result['errors'].append("Unauthorized access: Loan does not belong to this business")
            return validation_result

        validation_result['loan_data'] = loan_data

        # Check loan status
        current_status = loan_data.get('status', '').strip().capitalize()
        if current_status not in ['Active', 'Overdue', 'Default']:
            validation_result['is_valid'] = False
            validation_result['errors'].append(f"Cannot process repayment for loan with status: {current_status}")

        # Validate amount
        try:
            amount_float = float(amount)
            if amount_float <= 0:
                validation_result['is_valid'] = False
                validation_result['errors'].append("Repayment amount must be greater than 0")

            # Check if amount exceeds remaining balance
            current_loan_amount = float(loan_data.get('amount', 0))
            # Ideally replace with self.get_remaining_balance(loan_id, business_id)
            if amount_float > current_loan_amount:
                validation_result['warnings'].append(
                    f"Repayment amount ({amount_float}) exceeds remaining loan balance ({current_loan_amount})"
                )

        except (ValueError, TypeError):
            validation_result['is_valid'] = False
            validation_result['errors'].append("Invalid repayment amount")

        # Validate date format
        try:
            datetime.datetime.fromisoformat(repayment_date.replace('Z', '+00:00'))
        except ValueError:
            validation_result['is_valid'] = False
            validation_result['errors'].append(
                "Invalid repayment date format. Expected ISO 8601 format (e.g. 2025-07-24T10:00:00Z)")

        return validation_result


