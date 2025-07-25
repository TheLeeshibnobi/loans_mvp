from supabase import create_client, Client
import datetime
import os
import logging

import pandas as pd
import io
from flask import send_file, make_response


import tempfile
import os

from datetime import datetime


# Set up logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


class Expenses:
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

    def get_expense_types(self, business_id):
        """returns a list of expenses names from the table for that specific business id"""

        try:
            response = (
                self.supabase
                .table('expense_types')
                .select('name')
                .eq('business_id', business_id)
                .execute()
            )


            if not response.data:
                expenses = []

            expenses = response.data
            return expenses

        except Exception as e:
            print(f'Exception: {e}')

    def get_expenses(self, business_id):
        """returns a list of expenses data from the table for that specific business id"""

        try:
            response = (
                self.supabase
                .table('expenses')
                .select('*')
                .eq('business_id', business_id)
                .order('created_at', desc=True)
                .execute()
            )


            if not response.data:
                expense_data = []

            expense_data = response.data
            return expense_data

        except Exception as e:
            print(f'Exception: {e}')

    def total_expense_amount(self, business_id):
        """Returns the total expenses for that business"""
        try:
            response = (
                self.supabase
                .table('expenses')
                .select('amount')
                .eq('business_id', business_id)
                .execute()
            )

            if not response.data:
                return 0.00

            expense_total = float(sum(data['amount'] for data in response.data))
            return expense_total

        except Exception as e:
            print(f'Exception: {e}')
            return 0.00

    def add_expense_type(self, business_id, name):
        """Adds an expense type to the expense_types table for that business_id"""
        data = {
            'name': name,
            'business_id': business_id
        }

        try:
            response = self.supabase.table('expense_types').insert(data).execute()
            if response.data:
                print('Successfully uploaded expense type')
            else:
                print('Error uploading expense type')
        except Exception as e:
            print(f'Exception: {e}')

    def record_expense(self, business_id, name, amount):
        """records an expanse in the expense table for that business_id"""
        data = {
            'name': name,
            'business_id': business_id,
            'amount' : amount
        }

        try:
            response = self.supabase.table('expenses').insert(data).execute()
            if response.data:
                print('Successfully uploaded expense')
            else:
                print('Error uploading expense')
        except Exception as e:
            print(f'Exception: {e}')

    def get_expense_csv(self, business_id, start_date, end_date):  # Fixed parameter order
        """Returns a DataFrame of expenses for the given date range"""
        try:
            response = (
                self.supabase
                .table('expenses')
                .select('*')
                .eq('business_id', business_id)
                .gte('created_at', start_date)
                .lte('created_at', end_date)
                .execute()
            )

            if not response.data:
                return pd.DataFrame()

            return pd.DataFrame(response.data)

        except Exception as e:
            print(f'Exception: {e}')
            return pd.DataFrame()

    def download_csv(self, business_id, start_date, end_date):
        """Returns a Flask CSV download response of expenses for a specific business."""

        if not business_id:
            logger.error("business_id is required for CSV download")
            return make_response("Error: business_id is required", 400)

        try:
            # Get DataFrame
            df = self.get_expense_csv(business_id, start_date, end_date)

            if df.empty:
                logger.warning(f"No expenses found for business {business_id} between {start_date} and {end_date}")
                return make_response("No expenses found for the selected date range", 404)

            # Convert DataFrame to CSV string
            csv_string = df.to_csv(index=False)

            # Create BytesIO buffer
            csv_buffer = io.BytesIO()
            csv_buffer.write(csv_string.encode('utf-8'))
            csv_buffer.seek(0)

            filename = f"expenses_for_{business_id}_{start_date}_to_{end_date}.csv"

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

    def filter_expenses(self, business_id, from_date=None, to_date=None, name=None):
        """
        Returns a list of expenses filtered by business ID, optional date range, and optional expense name.
        """

        try:
            query = (
                self.supabase
                .table('expenses')
                .select('*')
                .eq('business_id', business_id)
            )

            # Apply date filters
            if from_date:
                query = query.gte('created_at', from_date)
            if to_date:
                query = query.lte('created_at', to_date)

            # Filter by expense name
            if name:
                query = query.eq('name', name)

            response = query.order('created_at', desc=True).execute()
            logger.debug(f'Fetched {len(response.data) if response.data else 0} expenses for business_id={business_id}')

            return response.data or []

        except Exception as e:
            logger.error(f'Exception in filter_expenses: {e}')
            return []


