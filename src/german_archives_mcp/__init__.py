"""An MCP server for German archives' finding aids and online vital registers.

Three sources. The Deutsche Digitale Bibliothek (DDB), with its archive
portal Archivportal-D, aggregates the finding aids and digitised objects of
German archives, libraries and museums behind one keyless API: the server
searches it and reads one entry with its place in the fonds. The
Landesarchiv Baden-Württemberg has digitised its nineteenth-century vital
registers (Baden's Standesbücher, Württemberg's and Hohenzollern's
church-book duplicates, the films of the Jewish registers), and the
Landesarchiv Nordrhein-Westfalen its civil registers: the server finds the
register for a place and a year and downloads one page image. Nothing here
writes anywhere, and nothing here keeps a family tree.
"""

__version__ = "0.2.0"
