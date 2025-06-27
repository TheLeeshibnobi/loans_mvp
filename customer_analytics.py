from numpy.ma.extras import average
from supabase import create_client, Client
from supabase import create_client, Client
import datetime
import os
from calendar import monthrange
from collections import Counter
from collections import defaultdict

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


class CustomerAnalytics:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

    def month_map(self, year: int):
        """Defines a month map with proper date ranges for a given year."""
        # Validate year range - Use datetime.MINYEAR and datetime.MAXYEAR
        if not isinstance(year, int) or not (datetime.MINYEAR <= year <= datetime.MAXYEAR):
            raise ValueError(f"Year must be an integer between {datetime.MINYEAR} and {datetime.MAXYEAR}, got: {year}")

        try:
            month_ranges = {
                month: (
                    f"{year}-{str(i).zfill(2)}-01T00:00:00+00:00",
                    f"{year}-{str(i).zfill(2)}-{monthrange(year, i)[1]}T23:59:59+00:00"
                )
                for i, month in enumerate([
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ], start=1)
            }

            # Add "All Months" as a special case
            month_ranges["All Months"] = (
                f"{year}-01-01T00:00:00+00:00",
                f"{year}-12-31T23:59:59+00:00"
            )

            return month_ranges
        except Exception as e:
            raise ValueError(f"Error creating month map for year {year}: {str(e)}")

    def apply_gender_filter(self, query, gender):
        """Applies gender filtering to a Supabase query."""
        if gender == "All":
            return query.or_("gender.eq.Male,gender.eq.Female")
        else:
            return query.eq("gender", gender)

    def total_customers(self, gender, month, year):
        """Returns the total number of customers based on gender, month, and year."""
        # Validate inputs
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                raise ValueError(f"Year must be a valid integer, got: {year}")

        start, end = self.month_map(year)[month]

        query = (self.supabase
                 .table("borrowers")
                 .select("nrc_number")
                 .gte("created_at", start)
                 .lte("created_at", end))

        query = self.apply_gender_filter(query, gender)

        response = query.execute()
        return len(response.data)

    def get_location_by_status(self, gender, year, month, statuses):
        """
        Returns the most common location among borrowers with given loan statuses
        (e.g., ['Overdue', 'Default'] for worst, ['Completed'] for best).
        """
        # Validate inputs
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                raise ValueError(f"Year must be a valid integer, got: {year}")

        start, end = self.month_map(year)[month]

        # Step 1: Build status filter string for Supabase .or_()
        status_filter = ",".join([f"status.eq.{s}" for s in statuses])

        # Step 2: Query loans with matching statuses
        loan_query = (self.supabase
                      .table("loans")
                      .select("borrower_id, status")
                      .or_(status_filter)
                      .gte("created_at", start)
                      .lte("created_at", end))

        loan_response = loan_query.execute()
        default_ids = [item['borrower_id'] for item in loan_response.data]

        # Step 3: Get borrower locations
        locations = []
        for borrower_id in default_ids:
            borrower_query = (self.supabase
                              .table('borrowers')
                              .select('location')
                              .eq('id', borrower_id))

            borrower_query = self.apply_gender_filter(borrower_query, gender)
            borrower_response = borrower_query.execute()

            data = borrower_response.data
            if data:
                locations.append(data[0]['location'])

        # Step 4: Return the most common location (with tie handling)
        if locations:
            location_counts = Counter(locations)
            max_count = max(location_counts.values())
            tied_locations = [loc for loc, count in location_counts.items() if count == max_count]
            return sorted(tied_locations)[0]  # Return alphabetically first of tied
        else:
            return "No data found"

    def worst_location(self, gender, year, month):
        return self.get_location_by_status(gender, year, month, ['Overdue', 'Default'])

    def best_location(self, gender, year, month):
        return self.get_location_by_status(gender, year, month, ['Completed'])

    def average_loan_amount(self, gender, year, month):
        """returns the average loan amount based on the gender, year, month"""
        # Validate inputs
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                raise ValueError(f"Year must be a valid integer, got: {year}")

        start, end = self.month_map(year)[month]

        borrower_query = (
            self.supabase
            .table('borrowers')
            .select('id')
            .gte("created_at", start)
            .lte("created_at", end)
        )
        query = self.apply_gender_filter(borrower_query, gender)
        response = query.execute()

        borrower_ids = [item['id'] for item in response.data]

        if borrower_ids:
            loan_query = (self.supabase
                          .table("loans")
                          .select("amount")
                          .in_("borrower_id", borrower_ids))

            loan_response = loan_query.execute()
            loan_amounts = [item['amount'] for item in loan_response.data]
        else:
            loan_amounts = []

        if not loan_amounts:
            return 0.0

        average_amount = sum(loan_amounts) / len(loan_amounts)
        return round(average_amount, 2)

    def count_loans_by_status(self, location_dict, status, year, month):
        """
        Counts the number of loans per location with a given status (or list of statuses).
        """
        # Validate inputs
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                raise ValueError(f"Year must be a valid integer, got: {year}")

        start, end = self.month_map(year)[month]
        town_loan_counts = {}

        for location, borrower_ids in location_dict.items():
            if borrower_ids:
                loan_query = (self.supabase
                              .table("loans")
                              .select("id")
                              .in_("borrower_id", borrower_ids)
                              .gte("created_at", start)
                              .lte("created_at", end))

                # Filter by status (supporting both string and list)
                # Only apply status filtering if it's not '*'
                if status != "*":
                    if isinstance(status, list):
                        status_filter = ",".join([f"status.eq.{s}" for s in status])
                        loan_query = loan_query.or_(status_filter)
                    else:
                        loan_query = loan_query.eq("status", status)

                loan_response = loan_query.execute()
                town_loan_counts[location] = len(loan_response.data)
            else:
                town_loan_counts[location] = 0

        return town_loan_counts

    def total_town_loans(self, gender, year, month):
        """
        Returns a dictionary of total loans given per town for a specific gender, year, and month.
        """
        # Step 1: Get all borrowers and group them by location
        borrower_query = (
            self.supabase
            .table('borrowers')
            .select('location', 'id')
        )

        query = self.apply_gender_filter(borrower_query, gender)
        response = query.execute()

        location_dict = defaultdict(list)
        for item in response.data:
            location_dict[item['location']].append(item['id'])
        location_dict = dict(location_dict)

        # Step 2: Use the reusable function to get loan counts (any status = all loans)
        return self.count_loans_by_status(location_dict, status="*", year=year, month=month)

    def total_town_completed_repayments(self, gender, year, month):
        """returns a dictionary of total loans that have been fully returned per town for a specific gender,
         year, and month"""
        # Step 1: Get all borrowers and group them by location
        borrower_query = (
            self.supabase
            .table('borrowers')
            .select('location', 'id')
        )

        query = self.apply_gender_filter(borrower_query, gender)
        response = query.execute()

        location_dict = defaultdict(list)
        for item in response.data:
            location_dict[item['location']].append(item['id'])
        location_dict = dict(location_dict)

        # Step 2: Use the reusable function to get loan counts (any status = all loans)
        return self.count_loans_by_status(location_dict, status="Completed", year=year, month=month)

    def location_performance_ranking(self, gender, year, month):
        """Returns a dictionary with towns ranked by repayment rate (highest first), formatted with %."""

        total_town_loans = self.total_town_loans(gender, year, month)
        total_town_completed_repayments = self.total_town_completed_repayments(gender, year, month)

        performance = {}

        for town, total_loans in total_town_loans.items():
            completed = total_town_completed_repayments.get(town, 0)

            if total_loans > 0:
                repayment_rate = round((completed / total_loans) * 100, 2)
            else:
                repayment_rate = 0.00

            performance[town] = repayment_rate

        # Sort by repayment rate descending
        sorted_performance = dict(
            sorted(performance.items(), key=lambda x: x[1], reverse=True)
        )

        # Convert values to string with "%"
        final_output = {town: f"{rate}%" for town, rate in sorted_performance.items()}

        return final_output

    def loans_by_occupation(self, gender, year, month):
        """returns a dictionary of occupations as keys and number of loans given to that occupation as values"""
        # Step 1: Get all borrowers and group them by location
        borrower_query = (
            self.supabase
            .table('borrowers')
            .select('occupation', 'id')
        )

        query = self.apply_gender_filter(borrower_query, gender)
        response = query.execute()

        occupation_dict = defaultdict(list)
        for item in response.data:
            occupation_dict[item['occupation']].append(item['id'])
        location_dict = dict(occupation_dict)

        # Step 2: Use the reusable function to get loan counts (any status = all loans)
        return self.count_loans_by_status(location_dict, status="*", year=year, month=month)

    def loans_by_age_group(self, gender, year, month):
        """returns a dictionary of age groups as keys and the total loans given to them as values"""
        borrower_query = (
            self.supabase
            .table('borrowers')
            .select('birth_date', 'id')
        )

        query = self.apply_gender_filter(borrower_query, gender)
        response = query.execute()

        today = datetime.datetime.today()
        for item in response.data:
            try:
                dob = datetime.datetime.strptime(item['birth_date'], "%Y-%m-%d")
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                item['age'] = age
            except (ValueError, TypeError):
                # Skip records with invalid birth dates
                item['age'] = None

            if 'birth_date' in item:
                del item['birth_date']

        age_groups = {
            "18-29": 0,
            "30-50": 0,
            "50-60": 0,
            "above 60": 0
        }

        for item in response.data:
            age = item.get('age')
            if age is not None:
                if 18 <= age <= 29:
                    age_groups["18-29"] += 1
                elif 30 <= age <= 50:
                    age_groups["30-50"] += 1
                elif 51 <= age <= 60:
                    age_groups["50-60"] += 1
                elif age > 60:
                    age_groups["above 60"] += 1

        return age_groups

    def loans_by_location_chart(self, gender, year, month):
        """returns an HTML string of a pie chart for loans by location"""
        try:
            loan_location_data = self.total_town_loans(gender, year,
                                                       month)  # dictionary of locations and count of loans

            # Check if data is empty
            if not loan_location_data:
                return "<div>No loan data available for the specified filters.</div>"

            # Convert dictionary to DataFrame
            df = pd.DataFrame(list(loan_location_data.items()), columns=['Location', 'Loan_Count'])

            # Sort by loan count in descending order
            df = df.sort_values('Loan_Count', ascending=False)

            # Create donut chart
            fig = go.Figure(data=[go.Pie(
                labels=df['Location'],
                values=df['Loan_Count'],
                hole=0.4,  # This creates the donut hole
                textinfo='label+percent',
                textposition='outside',
                marker=dict(
                    colors=px.colors.qualitative.Set3,  # Nice color palette
                    line=dict(color='#FFFFFF', width=2)
                )
            )])

            # Update layout
            fig.update_layout(
                title={
                    'text': f'Loans by Location - {gender.title()} ({month}/{year})',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 16, 'family': 'Arial, sans-serif'}
                },
                font=dict(size=12),
                showlegend=True,
                legend=dict(
                    orientation="v",
                    yanchor="middle",
                    y=0.5,
                    xanchor="left",
                    x=1.02
                ),
                margin=dict(l=20, r=120, t=60, b=20),
                #width=500,
                #height=300
            )

            # Convert to HTML string
            html_string = fig.to_html(include_plotlyjs='cdn', full_html=False, config={'responsive': True})

            return html_string
        except Exception as e:
            return f"<div>Error generating chart: {str(e)}</div>"

    def loans_by_occupation_chart(self, gender, year, month):
        """returns an HTML string of a bar chart for loans by occupation"""
        try:
            loans_occupation_data = self.loans_by_occupation(gender, year, month)

            # Check if data is empty
            if not loans_occupation_data:
                return "<div>No loan data available for the specified filters.</div>"

            # Convert dictionary to DataFrame
            df = pd.DataFrame(list(loans_occupation_data.items()), columns=['Occupation', 'Loan_Count'])

            # Sort by loan count in descending order
            df = df.sort_values('Loan_Count', ascending=False)

            # Create bar chart
            fig = go.Figure(data=[go.Bar(
                x=df['Occupation'],
                y=df['Loan_Count'],
                marker_color='#1f77b4',  # Blue color
                text=df['Loan_Count'],
                textposition='outside',
                textfont=dict(size=10)
            )])

            # Update layout
            fig.update_layout(
                title={
                    'text': f'Loans by Occupation - {gender.title()} ({month}/{year})',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 16, 'family': 'Arial, sans-serif'}
                },
                xaxis_title='Occupation',
                yaxis_title='Number of Loans',
                font=dict(size=10),
                margin=dict(l=40, r=20, t=60, b=80),
                #width=500,
                #height=300,
                xaxis=dict(
                    tickangle=45,  # Rotate x-axis labels for better readability
                    tickfont=dict(size=9)
                ),
                yaxis=dict(
                    tickfont=dict(size=10)
                )
            )

            # Convert to HTML string
            html_string = fig.to_html(include_plotlyjs='cdn', full_html=False, config={'responsive': True})

            return html_string
        except Exception as e:
            return f"<div>Error generating chart: {str(e)}</div>"

    def age_group_radial_bar_chart(self, gender, year, month):
        """returns an HTML string of a radial_bar_chart for loans by age group"""
        try:
            age_group_loans_data = self.loans_by_age_group(gender, year, month)

            # Check if data is empty
            if not age_group_loans_data:
                return "<div>No loan data available for the specified filters.</div>"

            # Convert dictionary to DataFrame
            df = pd.DataFrame(list(age_group_loans_data.items()), columns=['Age_Group', 'Loan_Count'])

            # Sort by age group for logical ordering
            df = df.sort_values('Age_Group')

            # Create radial bar chart using polar coordinates
            fig = go.Figure()

            # Add radial bars
            fig.add_trace(go.Barpolar(
                r=df['Loan_Count'],
                theta=df['Age_Group'],
                width=0.8,
                marker=dict(
                    color=['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD'],
                    line=dict(color='rgba(255,255,255,0.8)', width=1)
                ),
                opacity=0.8,
                text=df['Loan_Count']
            ))

            # Update layout for radial chart
            fig.update_layout(
                title={
                    'text': f'Loans by Age Group - {gender.title()} ({month}/{year})',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 16, 'family': 'Arial, sans-serif'}
                },
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, max(df['Loan_Count']) * 1.1],
                        tickfont=dict(size=9),
                        gridcolor='lightgray',
                        gridwidth=1
                    ),
                    angularaxis=dict(
                        tickfont=dict(size=10),
                        rotation=90,  # Start from top
                        direction='clockwise'
                    ),
                    bgcolor='rgba(255,255,255,0.9)'
                ),
                font=dict(size=10),
                margin=dict(l=40, r=40, t=60, b=40),
                #width=500,
                #height=300,
                showlegend=False
            )

            # Convert to HTML string
            html_string = fig.to_html(include_plotlyjs='cdn', full_html=False, config={'responsive': True})

            return html_string
        except Exception as e:
            return f"<div>Error generating chart: {str(e)}</div>"




