from supabase import create_client, Client
from datetime import date, timedelta, datetime, UTC, timezone
from dotenv import load_dotenv
import os
import json



class Loans:
    """Contains metrics for the overview dashboard"""

    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

    def borrower_identity(self, borrower_id):
        """Returns the name and NRC of that borrower"""

        response = (
            self.supabase
            .table('borrowers')
            .select('name', 'nrc_number')
            .eq('id', borrower_id)
            .execute()
        )

        raw_data = response.data

        if not raw_data:
            return {'name': 'Unknown', 'nrc': 'Unknown'}

        return {
            'name': raw_data[0]['name'],
            'nrc': raw_data[0]['nrc_number']
        }

    def old_borrower_loan(self, borrower_id, amount, transaction_costs, interest_rate,
                          duration_days, due_date, contract_file_obj, collateral_files_list, loan_reason):
        """Registers a loan for an already existing borrower in the database."""

        contract_file_url = None
        collateral_file_urls = []

        try:
            # Upload contract file if provided
            if contract_file_obj:
                contract_file_url = self.upload_contract_file(contract_file_obj, borrower_id)
                print(f"Contract file uploaded: {contract_file_url}")

            # Upload collateral files if provided
            if collateral_files_list:
                collateral_file_urls = self.upload_collateral_files_list(collateral_files_list, borrower_id)
                print(f"Collateral files uploaded: {len(collateral_file_urls)} files")

            # Insert loan data
            data = {
                'borrower_id': borrower_id,
                'amount': amount,
                'status': 'Active',
                'interest_rate': interest_rate,
                'duration_days': duration_days,
                'due_date': due_date,
                'transaction_costs': transaction_costs,
                'loan_reason' : loan_reason
            }

            print(f"Inserting loan data: {data}")
            response = self.supabase.table('loans').insert(data).execute()
            print("Loan inserted successfully:", response.data)

            if response.data and len(response.data) > 0 and 'id' in response.data[0]:
                loan_id = response.data[0]['id']
                print(f"Loan ID: {loan_id}")

                # Insert file data if we have either contract or collateral files
                if contract_file_url or collateral_file_urls:
                    file_data = {
                        'loan_id': loan_id,
                        'docs': [contract_file_url] if contract_file_url else [],
                        'photos': collateral_file_urls if collateral_file_urls else []
                    }

                    print(f"Inserting file data: {file_data}")
                    file_upload_response = self.supabase.table('files').insert(file_data).execute()
                    print("File data inserted:", file_upload_response.data)

                    # update available cash

                return loan_id
            else:
                print("Loan inserted but no ID returned.")
                return None

        except Exception as e:
            print("Error inserting loan:", e)
            import traceback
            traceback.print_exc()
            return None



    def upload_contract_file(self, contract_file_obj, borrower_id):
        """Uploads the contract file to the Supabase bucket and returns the file URL."""

        try:
            # Get borrower NRC
            nrc_response = (
                self.supabase
                .table('borrowers')
                .select('nrc_number')
                .eq('id', borrower_id)
                .execute()
            )

            if not nrc_response.data:
                raise ValueError("Borrower not found")

            nrc_number = nrc_response.data[0]['nrc_number']

            # Construct filename
            file_extension = contract_file_obj.filename.split('.')[-1]
            filename = f"loan_contract/nrc_{nrc_number}.{file_extension}"

            # Upload the file
            file_bytes = contract_file_obj.read()

            # Reset file pointer for potential re-reading
            contract_file_obj.seek(0)

            upload_response = self.supabase.storage.from_('contracts').upload(
                filename,
                file_bytes,
                {"content-type": contract_file_obj.content_type}
            )

            # Get the public URL (if bucket is public)
            public_url = self.supabase.storage.from_('contracts').get_public_url(filename)

            return public_url

        except Exception as e:
            print(f"Error uploading contract file: {e}")
            return None

    def upload_collateral_files_list(self, collateral_files_list, borrower_id):
        """Uploads collateral files to the Supabase bucket and returns list of file URLs."""

        try:
            # Get borrower NRC
            nrc_response = (
                self.supabase
                .table('borrowers')
                .select('nrc_number')
                .eq('id', borrower_id)
                .execute()
            )

            if not nrc_response.data:
                raise ValueError("Borrower not found")

            nrc_number = nrc_response.data[0]['nrc_number']
            uploaded_urls = []

            # Upload each collateral file
            for index, file_obj in enumerate(collateral_files_list):
                # Skip empty files
                if not file_obj or file_obj.filename == '':
                    continue

                # Construct filename
                file_extension = file_obj.filename.split('.')[-1]
                filename = f"collateral/nrc_{nrc_number}_collateral_{index + 1}.{file_extension}"

                # Upload the file
                file_bytes = file_obj.read()

                # Reset file pointer for potential re-reading
                file_obj.seek(0)

                print(f"Uploading collateral file: {filename}")
                upload_response = self.supabase.storage.from_('collaterals').upload(
                    filename,
                    file_bytes,
                    {"content-type": file_obj.content_type}
                )

                # Get the public URL
                public_url = self.supabase.storage.from_('collaterals').get_public_url(filename)
                uploaded_urls.append(public_url)
                print(f"Collateral file uploaded: {public_url}")

            return uploaded_urls

        except Exception as e:
            print(f"Error uploading collateral files: {e}")
            import traceback
            traceback.print_exc()
            return []





    def update_overdue_loans(self):
        now = datetime.now(timezone.utc)

        response = (
            self.supabase
            .table('loans')
            .select('id, due_date')
            .eq('status', 'Active')
            .execute()
        )

        loans = response.data

        overdue_ids = []
        for loan in loans:
            due_date_str = loan.get('due_date')
            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(due_date_str)

                    # If due_date is naive, make it UTC-aware by assuming UTC
                    if due_date.tzinfo is None:
                        due_date = due_date.replace(tzinfo=timezone.utc)

                    if due_date < now:
                        overdue_ids.append(loan['id'])
                except ValueError:
                    print(f"Invalid due_date format for loan id {loan['id']}: {due_date_str}")
            else:
                print(f"Missing due_date for loan id {loan['id']}")

        if overdue_ids:
            print(f"Updating {len(overdue_ids)} loans to Overdue.")
            self.supabase \
                .table('loans') \
                .update({'status': 'Overdue'}) \
                .in_('id', overdue_ids) \
                .execute()
        else:
            print("No overdue loans found.")
