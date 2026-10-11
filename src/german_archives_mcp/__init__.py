"""An MCP server for German archives' finding aids and Baden's civil registers.

Two sources. The Deutsche Digitale Bibliothek (DDB), with its archive portal
Archivportal-D, aggregates the finding aids and digitised objects of German
archives, libraries and museums behind one keyless API: the server searches
it and reads one entry with its place in the fonds. The Landesarchiv
Baden-Württemberg has digitised the Standesbücher of Baden, the civil
duplicates of the parish registers for about 1810 to 1870: the server finds
the book for a place and a year and downloads one page image. Nothing here
writes anywhere, and nothing here keeps a family tree.
"""

__version__ = "0.1.0"
