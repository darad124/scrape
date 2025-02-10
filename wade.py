import pandas as pd
import numpy as np

def fill_supplier(lookup_csv_path, target_csv_path):
    """
    Fills the 'operator' column in the target CSV using a lookup CSV,
    with a fallback to the 'information' column.
    Overwrites the original target CSV.
    """

    try:
        # Load the CSVs
        lookup_df = pd.read_csv(lookup_csv_path)
        target_df = pd.read_csv(target_csv_path)

        # Ensure consistent column names (strip whitespace)
        lookup_df.columns = lookup_df.columns.str.strip()
        target_df.columns = target_df.columns.str.strip()

        # Drop the 'Unnamed: 5' column from lookup_df if it exists
        if 'Unnamed: 5' in lookup_df.columns:
            lookup_df = lookup_df.drop(columns=['Unnamed: 5'])

        # --- Use Correct Column Names for ferry_schedules_final_final.csv ---
        # Add 'operator' column to target if not present
        if 'operator' not in target_df.columns:
            target_df['operator'] = np.nan  # Initialize the operator column

        # 1. Create a combined key for matching (Use correct column names!)
        lookup_df['MatchKey'] = (
            lookup_df['From'].str.strip() + "_" +
            lookup_df['To'].str.strip() + "_" +
            lookup_df['Departure'].str.strip()
        )
        target_df['MatchKey'] = (
            target_df['from_location'].str.strip() + "_" +
            target_df['to_location'].str.strip() + "_" +
            target_df['departure_time'].str.strip()
        )

        # 2. Group the lookup table by the MatchKey and get unique suppliers.
        lookup_grouped = lookup_df.groupby('MatchKey')['Supplier'].agg(lambda x: list(set(x))).reset_index()
        lookup_grouped.rename(columns={'Supplier': 'PossibleSuppliers'}, inplace=True)

        # 3. Merge the target data with the grouped lookup data.
        merged_df = pd.merge(target_df, lookup_grouped, on='MatchKey', how='left')

        # 4. Fill 'operator' based on uniqueness (primary method)
        def determine_supplier(row):
            if isinstance(row['PossibleSuppliers'], list) and len(row['PossibleSuppliers']) == 1:
                return row['PossibleSuppliers'][0]
            else:
                return np.nan  # Remain NaN if not unique (to use fallback)

        merged_df['operator'] = merged_df.apply(determine_supplier, axis=1)

        # 5. Fallback: Use the first word of the 'information' column if operator is still NaN.
        def fill_from_information(row):
            if pd.isna(row['operator']) and isinstance(row['information'], str) and row['information'].strip():
                first_word = row['information'].split()[0]
                # Check for specific words (using lower() for case-insensitive matching)
                if first_word.lower() == "over":
                    return "Raja ferry"
                elif first_word.lower() == "lomlahkkhirin":
                    return "Lomprahah"
                else:
                    return first_word  # Otherwise, use the first word as is
            else:
                return row['operator']  # Return the existing value if already set

        merged_df['operator'] = merged_df.apply(fill_from_information, axis=1)

        # --- Cleanup ---
        merged_df.drop(columns=['MatchKey', 'PossibleSuppliers'], inplace=True)

        # --- Save the result (OVERWRITING the original target CSV) ---
        merged_df.to_csv(target_csv_path, index=False)
        print(f"Operator information filled and saved to: {target_csv_path}")

    except FileNotFoundError:
        print("Error: One or both of the CSV files were not found.")
    except KeyError as e:
        print(f"Error: A required column is missing in one of the CSVs: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

# --- File Paths ---
lookup_csv_path = r"C:\Users\USER\Desktop\scrape\timetable.csv"
target_csv_path = r"C:\Users\USER\Desktop\scrape\ferry_schedules_final_final.csv"

# --- Run the Function ---
fill_supplier(lookup_csv_path, target_csv_path)

# Optional: Print the updated DataFrame (for verification)
try:
    updated_df = pd.read_csv(target_csv_path)
    print("\nTarget CSV after filling operator:")
    print(updated_df)
except FileNotFoundError:
    print("Could not print output.")
