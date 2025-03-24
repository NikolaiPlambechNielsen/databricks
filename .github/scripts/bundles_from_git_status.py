import json
import argparse
import re
from pathlib import PurePosixPath, Path
from pprint import pprint


class SnakeCaseError(Exception):
    pass


def get_bundles_from_files(file_paths, fourth_parent_name = None):
    table_bundles = set()
    view_bundles = set()

    for file in file_paths:

        file_path = Path(file)

        table_path = file_path.parent
        table_name = table_path.name

        if table_name[0] == '_' or table_name == 'tasks':
            # We hit one of the metadata folders, skip this
            continue

        schema_path = table_path.parent
        schema_name = schema_path.name
        if not schema_name or schema_name[0] == '_'  or schema_name == 'tasks':
            # We hit one of the metadata folders, skip this
            continue

        catalog_path = schema_path.parent
        catalog_name = catalog_path.name
        if not catalog_name or catalog_name[0] == '_':
            # We hit one of the metadata folders, skip this
            continue

        environment_path = catalog_path.parent
        environment_name = environment_path.name

        if fourth_parent_name is not None and environment_name != fourth_parent_name:
            raise ValueError(f'Fourth parent folder of {file} must be {fourth_parent_name}, but is {environment_name}')
        
        bundle_path = f'{catalog_name}/{schema_name}/{table_name}'

        # Searches for a .sql file starting with "load_".
        # If one is found, the folder corresponds to a table, and we break out of the loop
        # If one is not found (the loop runs until completion, triggering the else block), it is a view
        for bundle_file in table_path.iterdir():
            if bundle_file.name.startswith('load_') and bundle_file.suffix == '.sql':
                table_bundles.add(bundle_path)
                break
        else:
            view_bundles.add(bundle_path)

    return {'views': list(view_bundles), 'tables': list(table_bundles)}


def changed_files_from_all_lines(all_lines, workspace_folder):
    """Grabs file names of changed and added files from the list of all lines in the git status file.
    
    A git status files contains one line for each added/modified/deleted file, written in the following form:
    Status<tab>Name

    where "Status" is a one-letter code, either "A", "M" or "D" for added/modified/deleted, respectively.
    So we split the lines by tab-character, and if the status is either "A" or "M" we keep the file
    
    Note, "Status" can also be "R<SCORE>", where "R" means renamed, and <SCORE> is a file similarity score
    between 000 and 100.

    """

    changed_files = []
    for line in all_lines:
        components = line.split('\t')
        # First component is status name. We only want the first letter of this, to discard any score
        status = components[0][0]
        # The last component (second for "A", "M" and "D", and third for "R") is the file name.
        file = components[-1]
        is_status_correct = status in ('A', 'M', 'R')
        is_workspace_correct = file.split('/')[0] == workspace_folder  
        
        if is_status_correct and is_workspace_correct:
            changed_files.append(file)

    return changed_files


def validate_table_paths(changed_bundles: dict, ignore_case: bool = False):
    """Validate the paths for each bundle.

    The bundles are formatted as "{catalog}/{schema}/{table}", and we want to
    ensure each of these components are in snake_case with the Danish alphabet.
    
    Arguments:
    - changed_bundles: dict
        Output of get_bundles_from_files. Has two keys, "views" and "tables"
        each with a list of bundles as their value.
    - ignore_case: bool
        Whether or not to perform a case-insensitive search. Defaults to False.

    Raises:
    - NameError: 
    """

    view_paths = changed_bundles['views']
    table_paths = changed_bundles['tables']

    # The pattern we use searches the full string (as indicated by ^ and $,
    # which specifies start and end of string). It has three sets of characters
    # seperated by slashes (which are escaped by a backslash). Each set 
    # looks for a snake_case group, which allows all lowercase Danish
    # letters (a-å), underscores and digits.
    # The "ignore_case" argument relaxes the lowercase requirement.
    # Example that matches:
    # "this_is_a_catalog_name/this_is_a_schema/this_is_a_table"
    # Example that does not match:
    # "this_IS_a_catalog/this_is_a_schema/this_is_a_table"
    # Does not work, since there is a upper case "I" and "S" in the first set
    pattern = re.compile(r'^[a-z_\dæøå]+\/[a-z_\dæøå]+\/[a-z_\dæøå]+$')
    if ignore_case:
        pattern = re.compile(r'^[\w\dæøåÆØÅ]+\/[\w\dæøåÆØÅ]+\/[\w\dæøåÆØÅ]+$')

    view_errors = [view for view in view_paths if pattern.match(view) is None]
    table_errors = [table for table in table_paths if pattern.match(table) is None]
    
    error_string = ""
    # Build the list of "errors"
    if view_errors:
        all_view_errors = '\n'.join('- ' + i for i in view_errors)
        error_string += "The following views are named with characters that are not allowed:\n" \
                    + all_view_errors + '\n'
    if table_errors:
        all_table_errors = '\n'.join('- ' + i for i in table_errors)
        error_string += "The following views are named with characters that are not allowed:\n" \
                    + all_table_errors 

    # If there are any errors, we prepend the following string
    if error_string:
        not_string = '' if ignore_case else 'NOT '
        error_string = "Only Danish letters (a-z and æøå), digits and underscore is allowed in names.\n" \
             + f'Uppercase letters are {not_string}allowed.\n' + error_string

    if error_string:
        raise SnakeCaseError(error_string)
    

if __name__ == '__main__':
    # Add recognition of a single argument, the list of changed files, and grab it
    parser = argparse.ArgumentParser()
    parser.add_argument('git_status_file', type=Path, help='File containing list of changed files.')
    parser.add_argument('changed_bundles_path', type=Path, help='Path to the destination folder.')
    parser.add_argument('workspace_folder', type=str, help='Name of the workspace folder.')
    parser.add_argument('-i', '--ignore_case', action='store_true', help='Whether or not to ignore case when validating table names. ')
    args = parser.parse_args()

    with open(args.git_status_file, 'r', encoding='utf-8') as f: 
        # Load the environment variable as a JSON object.
        all_lines = f.readlines()
        changed_files = changed_files_from_all_lines(all_lines, workspace_folder=args.workspace_folder)

    changed_bundles = get_bundles_from_files(changed_files)

    # validate the file paths
    validate_table_paths(changed_bundles, ignore_case=args.ignore_case)

    with open(args.changed_bundles_path/'view_bundles.json', 'w', encoding='utf-8') as f:
        json.dump(changed_bundles.get('views'), f)

    with open(args.changed_bundles_path/'table_bundles.json', 'w', encoding='utf-8') as f:
        json.dump(changed_bundles.get('tables'), f)
