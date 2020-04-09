import os
import re
import datetime
from dateutil.parser import parse as dt_parser

# Parse metadata from filenames in a directory
###########################################
def metadata_parser(data_dir, meta_fields, valid_meta, meta_filters, date_format,
                    start_date, end_date, error_log, delimiter="_", file_type="png", coprocess=None):
    """Reads metadata the input data directory.

    Args:
        data_dir:     Input data directory.
        meta_fields:  Dictionary of image filename metadata fields and index positions.
        valid_meta:   Dictionary of valid metadata keys.
        meta_filters: Dictionary of metadata filters (key-value pairs).
        date_format:  Date format code for timestamp metadata to use with strptime
        start_date:   Analysis start date in Unix time.
        end_date:     Analysis end date in Unix time.
        error_log:    Error log filehandle object.
        delimiter:    Filename metadata delimiter string or regular expression pattern.
        file_type:    Image filetype extension (e.g. png).
        coprocess:    Coprocess the specified imgtype with the imgtype specified in meta_filters.

    Returns:
        jobcount:     The number of processing jobs.
        meta:         Dictionary of image metadata (one entry per image to be processed).

    :param data_dir: str
    :param meta_fields: dict
    :param valid_meta: dict
    :param meta_filters: dict
    :param date_format: str
    :param start_date: int
    :param end_date: int
    :param error_log: obj
    :param delimiter: str
    :param file_type: str
    :param coprocess: str
    :return jobcount: int
    :return meta: dict
    """

    # Metadata data structure
    meta = {}
    jobcount = 0

    # How many metadata fields are in the files we intend to process?
    meta_count = len(meta_fields.keys())

    # Compile regex (even if it's only a delimiter character)
    regex = re.compile(delimiter)

    # Check whether there is a snapshot metadata file or not
    if os.path.exists(os.path.join(data_dir, "SnapshotInfo.csv")):
        # Open the SnapshotInfo.csv file
        csvfile = open(os.path.join(data_dir, 'SnapshotInfo.csv'), 'r')

        # Read the first header line
        header = csvfile.readline()
        header = header.rstrip('\n')

        # Remove whitespace from the field names
        header = header.replace(" ", "")

        # Table column order
        cols = header.split(',')
        colnames = {}
        for i, col in enumerate(cols):
            colnames[col] = i

        # Read through the CSV file
        for row in csvfile:
            row = row.rstrip('\n')
            data = row.split(',')
            img_list = data[colnames['tiles']]
            if img_list[:-1] == ';':
                img_list = img_list[:-1]
            imgs = img_list.split(';')
            for img in imgs:
                if len(img) != 0:
                    dirpath = os.path.join(data_dir, 'snapshot' + data[colnames['id']])
                    filename = img + '.' + file_type
                    if not os.path.exists(os.path.join(dirpath, filename)):
                        error_log.write("Something is wrong, file {0}/{1} does not exist".format(dirpath, filename))
                        continue
                        # raise IOError("Something is wrong, file {0}/{1} does not exist".format(dirpath, filename))
                    # Metadata from image file name
                    metadata = _parse_filename(filename=img, delimiter=delimiter, regex=regex)
                    # Not all images in a directory may have the same metadata structure only keep those that do
                    if len(metadata) == meta_count:
                        # Image metadata
                        img_meta = {'path': dirpath}
                        img_pass = 1
                        coimg_store = 0
                        # For each of the type of metadata PlantCV keeps track of
                        for field in valid_meta:
                            # If the same metadata is found in the image filename, store the value
                            if field in meta_fields:
                                meta_value = metadata[meta_fields[field]]
                                # If the metadata type has a user-provided restriction
                                if field in meta_filters:
                                    # If the input value does not match an image value, fail the image
                                    # filter = meta_filters[field]
                                    # if meta_value != filter and (isinstance(filter, list) and not meta_value in field):
                                    filter = meta_filters[field]
                                    if isinstance(filter, list):
                                        if not meta_value in filter:
                                            img_pass = 0
                                    else:
                                        if meta_value != filter:
                                            img_pass = 0
                                img_meta[field] = meta_value
                            # If the same metadata is found in the CSV file, store the value
                            elif field in colnames:
                                meta_value = data[colnames[field]]
                                # If the metadata type has a user-provided restriction
                                if field in meta_filters:
                                    # If the input value does not match the image value, fail the image
                                    # filter = meta_filters[field]
                                    # if meta_value != filter and (isinstance(field, list) and not meta_value in field):
                                    filter = meta_filters[field]
                                    if isinstance(filter, list):
                                        if not meta_value in filter:
                                            img_pass = 0
                                    else:
                                        if meta_value != filter:
                                            img_pass = 0
                                img_meta[field] = meta_value
                            # Or use the default value
                            else:
                                img_meta[field] = valid_meta[field]["value"]

                        if start_date and end_date and img_meta['timestamp'] is not None:
                            in_date_range = check_date_range(start_date, end_date, img_meta['timestamp'], date_format)
                            if in_date_range is False:
                                img_pass = 0

                        if img_pass:
                            jobcount += 1

                        if coprocess is not None:
                            if img_meta['imgtype'] == coprocess:
                                coimg_store = 1

                        # If the image meets the user's criteria, store the metadata
                        if img_pass == 1:
                            # Link image to coprocessed image
                            coimg_pass = 0
                            if coprocess is not None:
                                for coimg in imgs:
                                    if len(coimg) != 0:
                                        meta_parts = _parse_filename(filename=coimg, delimiter=delimiter, regex=regex)
                                        if len(meta_parts) > 0:
                                            coimgtype = meta_parts[meta_fields['imgtype']]
                                            if coimgtype == coprocess:
                                                if 'camera' in meta_fields:
                                                    cocamera = meta_parts[meta_fields['camera']]
                                                    if 'frame' in meta_fields:
                                                        coframe = meta_parts[meta_fields['frame']]
                                                        if cocamera == img_meta['camera'] and coframe == img_meta['frame']:
                                                            img_meta['coimg'] = coimg + '.' + file_type
                                                            coimg_pass = 1
                                                    else:
                                                        if cocamera == img_meta['camera']:
                                                            img_meta['coimg'] = coimg + '.' + file_type
                                                            coimg_pass = 1
                                                else:
                                                    img_meta['coimg'] = coimg + '.' + file_type
                                                    coimg_pass = 1
                                if coimg_pass == 0:
                                    error_log.write(
                                        "Could not find an image to coprocess with " + os.path.join(dirpath,
                                                                                                    filename) + '\n')
                            meta[filename] = img_meta
                        elif coimg_store == 1:
                            meta[filename] = img_meta
    else:
        # Compile regular expression to remove image file extensions
        pattern = re.escape('.') + file_type + '$'
        ext = re.compile(pattern, re.IGNORECASE)

        # Walk through the input directory and find images that match input criteria
        for (dirpath, dirnames, filenames) in os.walk(data_dir):
            for filename in filenames:
                # Is filename and image?
                is_img = ext.search(filename)
                # If filename is an image, parse the metadata
                if is_img is not None:
                    # Remove the file extension
                    prefix = ext.sub('', filename)
                    metadata = _parse_filename(filename=prefix, delimiter=delimiter, regex=regex)

                    # Not all images in a directory may have the same metadata structure only keep those that do
                    if len(metadata) == meta_count:
                        # Image metadata
                        img_meta = {'path': dirpath}
                        img_pass = 1
                        # For each of the type of metadata PlantCV keeps track of
                        for field in valid_meta:
                            # If the same metadata is found in the image filename, store the value
                            if field in meta_fields:
                                meta_value = metadata[meta_fields[field]]
                                # If the metadata type has a user-provided restriction
                                if field in meta_filters:
                                    # If the input value does not match the image value, fail the image
                                    filter = meta_filters[field]
                                    if meta_value != filter and not meta_value in filter:
                                        img_pass = 0
                                img_meta[field] = meta_value
                            # Or use the default value
                            else:
                                img_meta[field] = valid_meta[field]["value"]

                        if start_date and end_date and img_meta['timestamp'] is not None:
                            in_date_range = check_date_range(start_date, end_date, img_meta['timestamp'], date_format)
                            if in_date_range is False:
                                img_pass = 0

                        # If the image meets the user's criteria, store the metadata
                        if img_pass == 1:
                            meta[filename] = img_meta
                            jobcount += 1

    return jobcount, meta
###########################################


# Check to see if the image was taken between a specified date range
###########################################
def check_date_range(start_date, end_date, img_time, date_format):
    """Check image time versus included date range.

    Args:
        start_date: Start date in Unix time
        end_date:   End date in Unix time
        img_time:   Image datetime
        date_format: date format code for strptime

    :param start_date: int
    :param end_date: int
    :param img_time: str
    :param date_format: str
    :return: bool
    """

    # Convert image datetime to unix time
    try:
        timestamp = datetime.datetime.strptime(img_time, date_format)
    except ValueError as e:
        raise SystemExit(str(e) + '\n  --> Please specify the correct --timestampformat argument <--\n')
    time_delta = timestamp - datetime.datetime(1970, 1, 1)
    unix_time = (time_delta.days * 24 * 3600) + time_delta.seconds
    # Does the image date-time fall outside or inside the included range
    if unix_time < start_date or unix_time > end_date:
        return False
    else:
        return True
###########################################


# Filename metadata parser
###########################################
def _parse_filename(filename, delimiter, regex):
    """Parse the input filename and return a list of metadata.

    Args:
        filename:   Filename to parse metadata from
        delimiter:  Delimiter character to split the filename on
        regex:      Compiled regular expression pattern to process file with

    :param filename: str
    :param delimiter: str
    :param regex: re.Pattern
    :return metadata: list
    """

    # Split the filename on delimiter if it is a single character
    if len(delimiter) == 1:
        metadata = filename.split(delimiter)
    else:
        metadata = re.search(regex, filename)
        if metadata is not None:
            metadata = list(metadata.groups())
        else:
            metadata = []
    return metadata
###########################################

def error_message(message, idx, match_string):
    """This function formats an error message that explains
    the problem and points out where in the user-provided line it
    occurred.

    Args:
        warning: Explanation of the problem
        idx:     Where to place the pointers

    :param warning: string
    :param index: int
    """
    message_and_original = message + "\n" + match_string
    point_out_error = " " * idx + "^"
    return message_and_original + "\n" + point_out_error

class ShowSourceOfError(ValueError):
    message = ""
    def __init__(self, index, source_string):
        super().__init__(error_message(self.message,
                                       index,
                                       source_string))

class EmptyKeyError(ShowSourceOfError):
    message = "Empty key"

class EmptyValueError(ShowSourceOfError):
    message = "Empty value"

class UnexpectedSpecialCharacterError(ShowSourceOfError):
    message = "Unexpected special character"

class MissingColonError(ShowSourceOfError):
    message = "Missing colon"

class KeyValuePairInListError(ShowSourceOfError):
    message = "Key-value pair in list"

class EmptyListError(ShowSourceOfError):
    message = "Empty list"

class OnlyCommaValidError(ShowSourceOfError):
    message = "Here, only a comma can follow a filter value"

class IncompleteKeyValuePairError(ShowSourceOfError):
    message = "Incomplete key-value pair"

class ParseMatchArg:

    special_characters = ":[],"

    def __init__(self, match_string):
        """This function initializes the parser with the string to be parsed.

        Args:
            match_string: The string to be parsed.

        :param match_string: str
        """
        self.match_string = match_string


    def parse(self):
        """
        Parse the match string and return a dictionary of filters.

        Args:
            match_string: String to be parsed

        :param match_string: str
        """
        self._tokenize_match_arg()
        return self._create_dictionary()


    def _flush_current_item(self, special, idx):
        """This function clears self.current_item and stores the previous value,
        along with information on the index of the token in the original string
        and whether it has a special meaning or is a regular string.

        Args:
            special: Whether the current item is special
            idx: The index where the current item can be found in original string

        :param special: bool
        :param idx: idt
        """
        if self.current_item != "":
            self.tokens.append(self.current_item)
            self.indices.append(idx)
            self.specials.append(special)
            self.current_item = ""


    def _tokenize_match_arg(self):
        """This function recognizes the special characters and
        clumps of normal characters within the match arg. For
        example:
        "id:[1,2]" -> ["id", ":", "[", "1", ",", "2", "]"]
        These intermediate results must be turned into a dictionary
        later.

        Args:
            match_string: String to be parsed

        :param match_string: str
        """
        self.tokens = []
        escaped = False
        active_quotes = []
        quote_symbols = ["'",'"']
        self.current_item = ""
        self.specials = []
        self.indices = []
        for idx, char in enumerate(self.match_string):
            if escaped:
                self.current_item += char
                escaped = False
            elif char in quote_symbols:
                if char in active_quotes:
                    quote_index = active_quotes.index(char)
                    active_quotes = active_quotes[:quote_index]
                    if quote_index != 0:
                        self.current_item += char
                else:
                    active_quotes.append(char)
            elif len(active_quotes) == 0:
                if char in self.special_characters:
                    self._flush_current_item(False, idx)
                    self.current_item += char
                    self._flush_current_item(special=True,idx=idx)
                elif char == "\\":
                    escaped = True
                elif char == ",":
                    self._flush_current_item(False, idx)
                    self.current_item += char
                    self._flush_current_item(True, idx)
                else:
                    self.current_item += char
            else:
                self.current_item += char
        self._flush_current_item(special=False, idx=idx)


    def _flush_value(self, current_value):
        """This function simply adds the argument to self.current_value_list

        Args:
            current_value: the value to be added

        :param current_value: string
        """
        self.current_value_list.append(current_value)


    def _flush_key_value(self):
        """This function clears the value of self.current_key and
        self.current_value_list, unless self.current_key is empty.
        If the key already exists, self.current_value_list will be
        added to the existing values, instead of replacing them.
        """
        if self.current_key is not None:
            if self.current_key in self.out:
                self.out[self.current_key].extend(self.current_value_list)
            else:
                self.out[self.current_key] = self.current_value_list
            self.current_value_list = []
            self.current_key = None


    def _create_dictionary(self):
        """
        This function converts the series of tokens returned by
        tokenize_match_arg into a dictionary mapping filter names
        to lists of valid patterns.

        While reading the list of tokens, the system can be in one of
        six possible states, each describing what is expected to come next:
            expecting_key: Expecting a key, e.g. the "key" in "key:value"
            expecting_colon: Expecting a colon
            expecting_value: Expecting a value, e.g. the "value" in "key:value"
            expecting_key_comma: Expecting a comma between key-value pairs, e.g. "a:b,c:d"
            expecting_list_comma: Expecting a comma inside a list, e.g. "[1,2]"
                                  The closing bracket is also a valid symbol
                                  here.
            expecting_list_value: Expecting a non-comma, non-bracket item
                                  inside a list
        The initial state is expecting_key. The state is stored in the variable
        mode.

        Here is an example of how a list of tokens might be parsed:

        Assume the string "id:[1a,2a]" has been parsed into the following three lists:
            self.tokens =  ["id",   ":",   "[",   "1a",   ",",   "2a",   "]"]
            self.special = [False,  True,  True,  False,  True,  False,  True]
            self.indices = [0,      2,     3,     4,      6,     7,      8]

       These will be represented with the following shorthand:
            tokens  id:[1a,2a]
            special F TTF TF T
            indices 0 234 67 8

        The function will iterate over self.tokens, self.special, and
        self.indices.
        In each iteration, the values will be stored in token, special, and
        idx.


        PERSISTENT on the left                           REPLACED EVERY LOOP on the right

        self.current_key = None
        self.current_value_list = []
        self.current_value = ""
        mode = "expecting_key"


        Iteration 1 id:[1a,2b] -----------------------------------------
                    F TTF TF T
                    0 234 67 9
                    ==
                                                         token = "id"
                                                         special = False
                                                         idx = 0

        self.current_key = "id"
        self.current_value_list = []
        self.current_value = ""
        mode = "expecting_colon"

        Iteration 2 id:[1a,2b] -----------------------------------------
                    F TTF TF T
                    0 234 67 9
                      =
                                                        token = ":"
                                                        special = True
                                                        idx = 2

        self.current_key = "id"
        self.current_value_list = []
        self.current_value = ""
        mode = "expecting_value"

        Iteration 3 id:[1a,2b] -----------------------------------------
                    F TTF TF T
                    0 234 67 9
                       =
                                                        token = "["
                                                        special = True
                                                        idx = 3

        self.current_key = "id"
        self.current_value_list = []
        self.current_value = ""
        mode = "expecting_list_value"

        Iteration 4 id:[1a,2b] -----------------------------------------
                    F TTF TF T
                    0 234 67 9
	                ==
                                                       token = "1"
                                                       special = False
                                                       idx = 4

        self.current_key = "id"
        self.current_value_list = ["1a"]
        self.current_value = ""
        mode = "expecting_list_comma"

        Iteration 5 id:[1a,2b] -----------------------------------------
                    F TTF TF T
                    0 234 67 9
                          =
                                                       token = ","
                                                       special = True
                                                       idx = 6

        self.current_key = "id"
        self.current_value_list = ["1a"]
        self.current_value = ""
        mode = "expecting_list_value"

        Iteration 6 id:[1a,2b] -----------------------------------------
                    F TTF TF T
                    0 234 67 9
                           ==
                                                       token = "2b"
                                                       special = False
                                                       idx = 7

        self.current_key = "id"
        self.current_value_list = ["1a","2b"]
        self.current_value = ""
        mode = "expecting_list_comma"

        Iteration 7 id:[1a,2b] -----------------------------------------
                    F TTF TF T
                    0 234 67 9
                             =
                                                       token = "]"
                                                       special = True
                                                       idx = 7

        self.current_key = "id"
        self.current_value_list = ["1a","2b"]
        self.current_value = ""
        mode = "expecting_key_comma"

        At this point, the key-value pair {"id":["1a","2b"]} will be added to self.out.

        Args:
            tokens: the text content of each token
            specials: whether each character is special or normal
            indices: where in the original string each token begins
            match_string: the original string being parsed

        :param tokens: list
        :param specials: list
        :param indices: list
        :param match_string: string
        """
        mode = "expecting_key"
        self.out = {}
        self.current_key = None
        self.current_value_list = []
        self.current_value = ""
        for token, special, idx, in zip(self.tokens,
                                        self.specials,
                                        self.indices):
            if mode == "expecting_key":
                if special:
                    #E.g. "camera:1,,"
                    raise IncompleteKeyValuePairError(idx,
                                                      self.match_string)
                else:
                    self.current_key = token
                    mode = "expecting_colon"
            elif mode == "expecting_colon" and special:
                if token == ":" and special:
                    mode = "expecting_value"
                else:
                    #E.g "camera:1,id,3"
                    raise MissingColonError(idx,
                                            self.match_string)
            elif mode == "expecting_value":
                if special and token != "[":
                    #E.g. "camera::"
                    raise UnexpectedSpecialCharacterError(idx,
                                                          self.match_string)
                elif token == "[" and special:
                    mode = "expecting_list_value"
                else:
                    self._flush_value(token)
                    self._flush_key_value()
                    mode = "expecting_key_comma"
            elif mode == "expecting_list_value":
                if token == ":" and special:
                    #E.g. "camera:[:]"
                    raise UnexpectedSpecialCharacterError(idx,
                                                          self.match_string)
                elif token == "]" and special:
                    if len(self.current_value_list) == 0:
                        #E.g. "camera:[]"
                        raise EmptyListError(idx,
                                             self.match_string)
                    else:
                        #E.g. "camera:[1,]"
                        raise EmptyValueError(idx,
                                              self.match_string)
                else:
                    self._flush_value(token)
                    mode = "expecting_list_comma"
            elif mode == "expecting_list_comma":
                if token == "]" and special:
                    self._flush_key_value()
                    mode = "expecting_key_comma"
                elif token == "," and special:
                    mode = "expecting_list_value"
                else:
                    #E.g. "camera:[1:2]"
                    raise OnlyCommaValidError(idx,
                                              self.match_string)
            elif mode == "expecting_key_comma":
                if not (token == "," and special):
                    #E.g. "camera:id:"
                    raise OnlyCommaValidError(idx,
                                              self.match_string)
                mode = "expecting_key"
        if mode == "expecting_value":
            #E.g. "camera:"
            raise EmptyValueError(idx + 1,
                                  self.match_string)
        elif mode == "expecting_key":
            #E.g. "camera:id,"
            raise EmptyKeyError(idx + 1,
                                self.match_string)
        elif mode == "expecting_colon":
            #E.g. "camera:1,2"
            raise IncompleteKeyValuePairError(idx + 1,
                                              self.match_string)
        self._flush_key_value()
        return self.out
