#!/usr/bin/env python3

import mimetypes
import sys

print(mimetypes.guess_type(sys.argv[1]), repr(sys.argv[1]))
