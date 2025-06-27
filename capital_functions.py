from supabase import create_client, Client
import datetime
import os


class CapitalFunctions:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

    def owners(self):
        """returns a list of owners from the owner's table"""
        response = (
            self.supabase
            .table('owners')
            .select('user_name')
            .execute()
        )

        data =  response.data
        owners = [owner['user_name'] for owner in data]
        return owners

    def get_owner_id(self, user_name):
        """Returns the owner id"""
        try:
            # Get an owner id from chosen name
            owner_response = (
                self.supabase
                .table('owners')
                .select('id')
                .eq('user_name', user_name)
                .execute()
            )

            if not owner_response.data:
                raise ValueError(f"Owner with user_name '{user_name}' not found")

            owner_id = owner_response.data[0]['id']
            return owner_id

        except Exception as e:
            print(f"Error getting owner ID: {e}")
            return None

    def upload_transaction_file(self, transaction_file_obj, owner_id):
        """Uploads the transaction file to the Supabase bucket and returns the file URL."""

        try:
            # Get owner name
            owner_response = (
                self.supabase
                .table('owners')
                .select('user_name')
                .eq('id', owner_id)
                .execute()
            )

            if not owner_response.data:
                raise ValueError("Owner not found")

            owner_user_name = owner_response.data[0]['user_name']

            # Construct filename
            file_extension = transaction_file_obj.filename.split('.')[-1]
            filename = f"equity_transactions/user_{owner_user_name}.{file_extension}"

            # Upload the file
            file_bytes = transaction_file_obj.read()

            # Reset file pointer for potential re-reading
            transaction_file_obj.seek(0)

            upload_response = self.supabase.storage.from_('equity').upload(
                filename,
                file_bytes,
                {"content-type": transaction_file_obj.content_type}
            )

            # Get the public URL (using the same bucket)
            public_url = self.supabase.storage.from_('equity').get_public_url(filename)

            return public_url

        except Exception as e:
            print(f"Error uploading transaction file: {e}")
            return None

    def record_given_dividend(self, amount, status, user_name, transaction_file_obj=None):
        """Registers a dividend in the disbursement table, with error handling."""

        transaction_files_urls = None

        # Get owner_id
        owner_id = self.get_owner_id(user_name)
        if not owner_id:
            return None

        try:
            # Upload transaction_file file if provided
            if transaction_file_obj:
                transaction_files_urls = self.upload_transaction_file(transaction_file_obj, owner_id)
                if transaction_files_urls:
                    print(f"Transaction file uploaded: {transaction_files_urls}")

            # Upload to disbursement table
            data = {
                'owner_id': owner_id,
                'amount': amount,
                'status': status
            }

            disbursement_response = self.supabase.table('disbursements').insert(data).execute()

            # Upload to the equity_files table
            if transaction_files_urls:
                equity_files_data = {
                    'transaction_type': 'disbursement',
                    'files': transaction_files_urls,
                    'owner_id': owner_id
                }

                equity_files_response = self.supabase.table('equity_files').insert(equity_files_data).execute()

            print(f"Dividend recorded successfully for {user_name}")
            return disbursement_response

        except Exception as e:
            print(f"Error while recording dividend: {e}")
            return None

    def record_capital_injection(self, user_name, amount, status, transaction_file_obj=None):
        """Records a capital injection into the injection table in the database"""

        transaction_files_urls = None

        # Get owner_id
        owner_id = self.get_owner_id(user_name)
        if not owner_id:
            return None

        try:
            # Upload transaction_file file if provided
            if transaction_file_obj:
                transaction_files_urls = self.upload_transaction_file(transaction_file_obj, owner_id)
                if transaction_files_urls:
                    print(f"Transaction file uploaded: {transaction_files_urls}")

            # Insert into injections table
            data = {
                'owner_id': owner_id,
                'amount': amount,
                'status': status
            }

            response = self.supabase.table('injections').insert(data).execute()

            # Upload to the equity_files table
            if transaction_files_urls:
                equity_files_data = {
                    'transaction_type': 'injection',
                    'files': transaction_files_urls,
                    'owner_id': owner_id
                }

                equity_files_response = self.supabase.table('equity_files').insert(equity_files_data).execute()

            print(f"Capital injection recorded successfully for {user_name}")
            return response

        except Exception as e:
            print(f"Error while recording capital injection: {e}")
            return None

# Test the module (commented out for production)
