-- Precheck (run BEFORE the matcher): confirm the 15 values are the real data domain.
-- Run on IBM i (STRSQL / Run SQL Scripts / ACS). Feed the results back to the maintainer.

-- 1) Actual DISTINCT domain and counts.
SELECT <column_name> AS grpmbr, COUNT(*) AS cnt
FROM <library>.<table>
GROUP BY <column_name>
ORDER BY 1;

-- Interpretation:
--   exactly the 15 values        -> anchor A can be the primary detector.
--   a 16th value appears          -> pure list matching has a blind spot; make anchor B
--                                    (field reference) primary, A secondary, and merge the
--                                    new value into config.GMAB_VALUES AFTER human confirmation
--                                    (the tool never changes the set on its own).

-- 2) Confirm the real column name / aliases (fill into config.FIELD_NAMES).
SELECT TABLE_NAME, COLUMN_NAME, LENGTH, CCSID
FROM QSYS2.SYSCOLUMNS
WHERE COLUMN_NAME LIKE '%GRP%' OR COLUMN_NAME LIKE '%MBR%' OR COLUMN_NAME LIKE '%MEMBER%'
ORDER BY TABLE_NAME, COLUMN_NAME;
