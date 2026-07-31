Small. Fast. Reliable.
Choose any three.  

- Home 
- Menu 
- About 
- Documentation 
- Download 
- License 
- Support 
- Purchase 
-  Search   

- About 
- Documentation 
- Download 
- Support 
- Purchase   
   Search Documentation Search Changelog        

# Rowid Tables

## 1.0 Definition

A "rowid table" is any table in an SQLite schema that  
- is not a virtual table, and 
- is not a WITHOUT ROWID table.  Most tables in a typical SQLite database schema are rowid tables. 
Rowid tables are distinguished by the fact that they all have a unique, non-NULL, signed 64-bit integer rowid that is used as the access key for the data in the underlying B-tree storage engine. 

## 2.0 Quirks

- 
 The PRIMARY KEY of a rowid table (if there is one) is usually not the true primary key for the table, in the sense that it is not the unique key used by the underlying B-tree storage engine. The exception to this rule is when the rowid table declares an INTEGER PRIMARY KEY. In the exception, the INTEGER PRIMARY KEY becomes an alias for the rowid. 
- 
 The true primary key for a rowid table (the value that is used as the key to look up rows in the underlying B-tree storage engine) is the rowid. 
- 
 The PRIMARY KEY constraint for a rowid table (as long as it is not the true primary key or INTEGER PRIMARY KEY) is really the same thing as a UNIQUE constraint. Because it is not a true primary key, columns of the PRIMARY KEY are allowed to be NULL, in violation of all SQL standards. 
- 
 The rowid of a rowid table can be accessed (or changed) by reading or writing to any of the "rowid" or "oid" or "_rowid_" columns. Except, if there are declared columns in the table that use any of those special names, then those names refer to the declared columns, not to the underlying rowid. 
- 
 Access to records via rowid is highly optimized and very fast. 
- 
 If the rowid is not aliased by INTEGER PRIMARY KEY then it is not persistent and might change. In particular the VACUUM command will change rowids for tables that do not declare an INTEGER PRIMARY KEY. Therefore, applications should not normally access the rowid directly, but instead use an INTEGER PRIMARY KEY. 
- 
 In the underlying file format, each rowid is stored as a variable-length integer. That means that small non-negative rowid values take up less disk space than large or negative rowid values. 
- 
 All of the complications above (and others not mentioned here) arise from the need to preserve backwards compatibility for the hundreds of billions of SQLite database files in circulation. In a perfect world, there would be no such thing as a "rowid" and all tables would following the standard semantics implemented as WITHOUT ROWID tables, only without the extra "WITHOUT ROWID" keywords. Unfortunately, life is messy. The designer of SQLite offers his sincere apology for the current mess.  
This page was last updated on 2025-05-31 13:08:22Z
