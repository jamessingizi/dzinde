"""Database layer: RootsMagic-11-compatible SQLite schema (.rmtree), seed data, helpers.

Schema text was recovered from the RootsMagic 11.5 binary (UTF-16 SQL literals), so files
created here open the same table layout RootsMagic uses, and RootsMagic files open here.
"""
import os
import sqlite3
import time
import uuid

OWNER = {'person': 0, 'family': 1, 'event': 2, 'source': 3, 'citation': 4, 'place': 5,
         'task': 6, 'name': 7, 'media': 11, 'placedetail': 14, 'repository': 18, 'fan': 19}

SCHEMA = """
CREATE TABLE IF NOT EXISTS AddressLinkTable (LinkID INTEGER PRIMARY KEY, OwnerType INTEGER, AddressID INTEGER, OwnerID INTEGER, AddressNum INTEGER, Details TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS AddressTable (AddressID INTEGER PRIMARY KEY, AddressType INTEGER, Name TEXT COLLATE RMNOCASE, Street1 TEXT, Street2 TEXT, City TEXT, State TEXT, Zip TEXT, Country TEXT, Phone1 TEXT, Phone2 TEXT, Fax TEXT, Email TEXT, URL TEXT, Latitude INTEGER, Longitude INTEGER, Note TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS AncestryTable (LinkID INTEGER PRIMARY KEY, LinkType INTEGER, rmID INTEGER, anID TEXT, Modified INTEGER, anVersion TEXT, anDate FLOAT, Status INTEGER, UTCModDate FLOAT, TreeID TEXT);
CREATE TABLE IF NOT EXISTS ChangeTable (RecID INTEGER PRIMARY KEY, OwnerType INTEGER, OwnerID INTEGER, Date FLOAT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS ChildTable (RecID INTEGER PRIMARY KEY, ChildID INTEGER, FamilyID INTEGER, RelFather INTEGER, RelMother INTEGER, ChildOrder INTEGER, IsPrivate INTEGER, ProofFather INTEGER, ProofMother INTEGER, Note TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS CitationLinkTable (LinkID INTEGER PRIMARY KEY, CitationID INTEGER, OwnerType INTEGER, OwnerID INTEGER, SortOrder INTEGER, Quality TEXT, IsPrivate INTEGER, Flags INTEGER, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS CitationTable (CitationID INTEGER PRIMARY KEY, SourceID INTEGER, Comments TEXT, ActualText TEXT, RefNumber TEXT, Footnote TEXT, ShortFootnote TEXT, Bibliography TEXT, Fields BLOB, UTCModDate FLOAT, CitationName TEXT COLLATE RMNOCASE);
CREATE TABLE IF NOT EXISTS ConfigTable (RecID INTEGER PRIMARY KEY, RecType INTEGER, Title TEXT, DataRec BLOB, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS DNATable (RecID INTEGER PRIMARY KEY, ID1 INTEGER, ID2 INTEGER, Label1 TEXT, Label2 TEXT, DNAProvider INTEGER, SharedCM FLOAT, SharedPercent FLOAT, LargeSeg FLOAT, SharedSegs INTEGER, Date TEXT, Relate1 INTEGER, Relate2 INTEGER, CommonAnc INTEGER, CommonAncType INTEGER, Verified INTEGER, Note TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS EventTable (EventID INTEGER PRIMARY KEY, EventType INTEGER, OwnerType INTEGER, OwnerID INTEGER, FamilyID INTEGER, PlaceID INTEGER, SiteID INTEGER, Date TEXT, SortDate BIGINT, IsPrimary INTEGER, IsPrivate INTEGER, Proof INTEGER, Status INTEGER, Sentence TEXT, Details TEXT, Note TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS ExclusionTable (RecID INTEGER PRIMARY KEY, ExclusionType INTEGER, ID1 INTEGER, ID2 INTEGER, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS FANTable (FanID INTEGER PRIMARY KEY, ID1 INTEGER, ID2 INTEGER, FanTypeID INTEGER, PlaceID INTEGER, SiteID INTEGER, Date TEXT, SortDate BIGINT, Description TEXT, Note TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS FANTypeTable (FANTypeID INTEGER PRIMARY KEY, Name TEXT COLLATE RMNOCASE, Role1 TEXT, Role2 TEXT, Sentence1 TEXT, Sentence2 TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS FactTypeTable (FactTypeID INTEGER PRIMARY KEY, OwnerType INTEGER, Name TEXT COLLATE RMNOCASE, Abbrev TEXT, GedcomTag TEXT, UseValue INTEGER, UseDate INTEGER, UsePlace INTEGER, Sentence TEXT, Flags INTEGER, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS FamilySearchTable (LinkID INTEGER PRIMARY KEY, LinkType INTEGER, rmID INTEGER, fsID TEXT, Modified INTEGER, fsVersion TEXT, fsDate FLOAT, Status INTEGER, UTCModDate FLOAT, TreeID TEXT);
CREATE TABLE IF NOT EXISTS FamilyTable (FamilyID INTEGER PRIMARY KEY, FatherID INTEGER, MotherID INTEGER, ChildID INTEGER, HusbOrder INTEGER, WifeOrder INTEGER, IsPrivate INTEGER, Proof INTEGER, SpouseLabel INTEGER, FatherLabel INTEGER, MotherLabel INTEGER, SpouseLabelStr TEXT, FatherLabelStr TEXT, MotherLabelStr TEXT, Note TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS GroupTable (RecID INTEGER PRIMARY KEY, GroupID INTEGER, StartID INTEGER, EndID INTEGER, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS HealthTable (RecID INTEGER PRIMARY KEY, OwnerID INTEGER, Condition INTEGER, SubCondition TEXT, Date FLOAT, Note TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS MediaLinkTable (LinkID INTEGER PRIMARY KEY, MediaID INTEGER, OwnerType INTEGER, OwnerID INTEGER, IsPrimary INTEGER, Include1 INTEGER, Include2 INTEGER, Include3 INTEGER, Include4 INTEGER, SortOrder INTEGER, RectLeft INTEGER, RectTop INTEGER, RectRight INTEGER, RectBottom INTEGER, Comments TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS MultimediaTable (MediaID INTEGER PRIMARY KEY, MediaType INTEGER, MediaPath TEXT, MediaFile TEXT COLLATE RMNOCASE, URL TEXT, Thumbnail BLOB, Caption TEXT COLLATE RMNOCASE, RefNumber TEXT COLLATE RMNOCASE, Date TEXT, SortDate BIGINT, Description TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS NameTable (NameID INTEGER PRIMARY KEY, OwnerID INTEGER, Surname TEXT COLLATE RMNOCASE, Given TEXT COLLATE RMNOCASE, Prefix TEXT COLLATE RMNOCASE, Suffix TEXT COLLATE RMNOCASE, Nickname TEXT COLLATE RMNOCASE, NameType INTEGER, Date TEXT, SortDate BIGINT, IsPrimary INTEGER, IsPrivate INTEGER, Proof INTEGER, Sentence TEXT, Note TEXT, BirthYear INTEGER, DeathYear INTEGER, Display INTEGER, Language TEXT, UTCModDate FLOAT, SurnameMP TEXT, GivenMP TEXT, NicknameMP TEXT);
CREATE TABLE IF NOT EXISTS PayloadTable (RecID INTEGER PRIMARY KEY, RecType INTEGER, OwnerType INTEGER, OwnerID INTEGER, Title TEXT, DataRec BLOB, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS PersonTable (PersonID INTEGER PRIMARY KEY, UniqueID TEXT, Sex INTEGER, ParentID INTEGER, SpouseID INTEGER, Color INTEGER, Color1 INTEGER, Color2 INTEGER, Color3 INTEGER, Color4 INTEGER, Color5 INTEGER, Color6 INTEGER, Color7 INTEGER, Color8 INTEGER, Color9 INTEGER, Relate1 INTEGER, Relate2 INTEGER, Flags INTEGER, Living INTEGER, IsPrivate INTEGER, Proof INTEGER, Bookmark INTEGER, Note TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS PlaceTable (PlaceID INTEGER PRIMARY KEY, PlaceType INTEGER, Name TEXT COLLATE RMNOCASE, Abbrev TEXT, Normalized TEXT, Latitude INTEGER, Longitude INTEGER, LatLongExact INTEGER, MasterID INTEGER, Note TEXT, Reverse TEXT COLLATE RMNOCASE, fsID INTEGER, anID INTEGER, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS RoleTable (RoleID INTEGER PRIMARY KEY, RoleName TEXT COLLATE RMNOCASE, EventType INTEGER, RoleType INTEGER, Sentence TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS SourceTable (SourceID INTEGER PRIMARY KEY, Name TEXT COLLATE RMNOCASE, RefNumber TEXT, ActualText TEXT, Comments TEXT, IsPrivate INTEGER, TemplateID INTEGER, Fields BLOB, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS SourceTemplateTable (TemplateID INTEGER PRIMARY KEY, Name TEXT COLLATE RMNOCASE, Description TEXT, Favorite INTEGER, Category TEXT, Footnote TEXT, ShortFootnote TEXT, Bibliography TEXT, FieldDefs BLOB, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS TagTable (TagID INTEGER PRIMARY KEY, TagType INTEGER, TagValue INTEGER, TagName TEXT COLLATE RMNOCASE, Description TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS TaskLinkTable (LinkID INTEGER PRIMARY KEY, TaskID INTEGER, OwnerType INTEGER, OwnerID INTEGER, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS TaskTable (TaskID INTEGER PRIMARY KEY, TaskType INTEGER, RefNumber TEXT, Name TEXT COLLATE RMNOCASE, Status INTEGER, Priority INTEGER, Date1 TEXT, Date2 TEXT, Date3 TEXT, SortDate1 BIGINT, SortDate2 BIGINT, SortDate3 BIGINT, Filename TEXT, Details TEXT, Results TEXT, UTCModDate FLOAT, Exclude INTEGER);
CREATE TABLE IF NOT EXISTS URLTable (LinkID INTEGER PRIMARY KEY, OwnerType INTEGER, OwnerID INTEGER, LinkType INTEGER, Name TEXT, URL TEXT, Note TEXT, UTCModDate FLOAT);
CREATE TABLE IF NOT EXISTS WitnessTable (WitnessID INTEGER PRIMARY KEY, EventID INTEGER, PersonID INTEGER, WitnessOrder INTEGER, Role INTEGER, Sentence TEXT, Note TEXT, Given TEXT COLLATE RMNOCASE, Surname TEXT COLLATE RMNOCASE, Prefix TEXT COLLATE RMNOCASE, Suffix TEXT COLLATE RMNOCASE, UTCModDate FLOAT);
CREATE INDEX IF NOT EXISTS idxAddressName ON AddressTable (Name);
CREATE INDEX IF NOT EXISTS idxChangeID ON ChangeTable (OwnerID);
CREATE INDEX IF NOT EXISTS idxChildFamilyID ON ChildTable (FamilyID);
CREATE INDEX IF NOT EXISTS idxChildID ON ChildTable (ChildID);
CREATE INDEX IF NOT EXISTS idxChildOrder ON ChildTable (ChildOrder);
CREATE INDEX IF NOT EXISTS idxCitationLinkOwnerID ON CitationLinkTable (OwnerID);
CREATE INDEX IF NOT EXISTS idxCitationName ON CitationTable (CitationName);
CREATE INDEX IF NOT EXISTS idxCitationSourceID ON CitationTable (SourceID);
CREATE INDEX IF NOT EXISTS idxDnaId1 ON DNATable (ID1);
CREATE INDEX IF NOT EXISTS idxDnaId2 ON DNATable (ID2);
CREATE INDEX IF NOT EXISTS idxFactTypeAbbrev ON FactTypeTable (Abbrev);
CREATE INDEX IF NOT EXISTS idxFactTypeGedcomTag ON FactTypeTable (GedcomTag);
CREATE INDEX IF NOT EXISTS idxFactTypeName ON FactTypeTable (Name);
CREATE INDEX IF NOT EXISTS idxFamilyFatherID ON FamilyTable (FatherID);
CREATE INDEX IF NOT EXISTS idxFamilyMotherID ON FamilyTable (MotherID);
CREATE INDEX IF NOT EXISTS idxFanId1 ON FANTable (ID1);
CREATE INDEX IF NOT EXISTS idxFanId2 ON FANTable (ID2);
CREATE INDEX IF NOT EXISTS idxFANTypeName ON FANTypeTable (Name);
CREATE INDEX IF NOT EXISTS idxGiven ON NameTable (Given);
CREATE INDEX IF NOT EXISTS idxGivenMP ON NameTable (GivenMP);
CREATE INDEX IF NOT EXISTS idxHealthOwnerId ON HealthTable (OwnerID);
CREATE INDEX IF NOT EXISTS idxLinkAncestryanID ON AncestryTable (anID);
CREATE INDEX IF NOT EXISTS idxLinkAncestryRmId ON AncestryTable (rmID);
CREATE INDEX IF NOT EXISTS idxLinkfsID ON FamilySearchTable (fsID);
CREATE INDEX IF NOT EXISTS idxLinkRmId ON FamilySearchTable (rmID);
CREATE INDEX IF NOT EXISTS idxMediaFile ON MultimediaTable (MediaFile);
CREATE INDEX IF NOT EXISTS idxMediaOwnerID ON MediaLinkTable (OwnerID);
CREATE INDEX IF NOT EXISTS idxMediaURL ON MultimediaTable (URL);
CREATE INDEX IF NOT EXISTS idxNameOwnerID ON NameTable (OwnerID);
CREATE INDEX IF NOT EXISTS idxNamePrimary ON NameTable (IsPrimary);
CREATE INDEX IF NOT EXISTS idxOwnerDate ON EventTable (OwnerID,SortDate);
CREATE INDEX IF NOT EXISTS idxOwnerEvent ON EventTable (OwnerID,EventType);
CREATE INDEX IF NOT EXISTS idxPayloadType ON PayloadTable (RecType);
CREATE INDEX IF NOT EXISTS idxPlaceAbbrev ON PlaceTable (Abbrev);
CREATE INDEX IF NOT EXISTS idxPlaceName ON PlaceTable (Name);
CREATE INDEX IF NOT EXISTS idxRecType ON ConfigTable (RecType);
CREATE INDEX IF NOT EXISTS idxReversePlaceName ON PlaceTable (Reverse);
CREATE INDEX IF NOT EXISTS idxRoleEventType ON RoleTable (EventType);
CREATE INDEX IF NOT EXISTS idxSourceName ON SourceTable (Name);
CREATE INDEX IF NOT EXISTS idxSourceTemplateName ON SourceTemplateTable (Name);
CREATE INDEX IF NOT EXISTS idxSurname ON NameTable (Surname);
CREATE INDEX IF NOT EXISTS idxSurnameGiven ON NameTable (Surname, Given, BirthYear, DeathYear);
CREATE INDEX IF NOT EXISTS idxSurnameGivenMP ON NameTable (SurnameMP, GivenMP, BirthYear, DeathYear);
CREATE INDEX IF NOT EXISTS idxSurnameMP ON NameTable (SurnameMP);
CREATE INDEX IF NOT EXISTS idxTagType ON TagTable (TagType);
CREATE INDEX IF NOT EXISTS idxTaskName ON TaskTable (Name);
CREATE INDEX IF NOT EXISTS idxTaskOwnerID ON TaskLinkTable (OwnerID);
CREATE INDEX IF NOT EXISTS idxURLOwnerID ON URLTable (OwnerID);
CREATE INDEX IF NOT EXISTS idxWitnessEventID ON WitnessTable (EventID);
CREATE INDEX IF NOT EXISTS idxWitnessPersonID ON WitnessTable (PersonID);
CREATE UNIQUE INDEX IF NOT EXISTS idxExclusionIndex ON ExclusionTable (ExclusionType, ID1, ID2);
"""

# Built-in fact types: (id, owner 0=person 1=family, name, abbrev, gedcom tag, use value/date/place, sentence).
# IDs follow the RootsMagic numbering (1 Birth, 2 Death, 300 Marriage, ...); the 1000+ block is our choice.
_S = '< [Date]>< [PlaceDetails]>< [Place]>.'
FACT_TYPES = [
    (1, 0, 'Birth', 'Birth', 'BIRT', 0, 1, 1, '[person] was born' + _S),
    (2, 0, 'Death', 'Death', 'DEAT', 1, 1, 1, '[person] died< [Desc]>< [Date]>< [person:Age]>< [PlaceDetails]>< [Place]>.'),
    (3, 0, 'Christen', 'Christen', 'CHR', 0, 1, 1, '[person] was christened' + _S),
    (4, 0, 'Burial', 'Burial', 'BURI', 0, 1, 1, '[person] was buried' + _S),
    (5, 0, 'Cremation', 'Cremation', 'CREM', 0, 1, 1, '[person] was cremated' + _S),
    (6, 0, 'Adoption', 'Adoption', 'ADOP', 0, 1, 1, '[person] was adopted' + _S),
    (7, 0, 'Baptism', 'Baptism', 'BAPM', 0, 1, 1, '[person] was baptized' + _S),
    (8, 0, 'Bar Mitzvah', 'Bar Mitzvah', 'BARM', 0, 1, 1, '[person] celebrated his bar mitzvah' + _S),
    (9, 0, 'Bas Mitzvah', 'Bas Mitzvah', 'BASM', 0, 1, 1, '[person] celebrated her bas mitzvah' + _S),
    (10, 0, 'Blessing', 'Blessing', 'BLES', 0, 1, 1, '[person] was blessed' + _S),
    (11, 0, 'Christen (adult)', 'Chr (adult)', 'CHRA', 0, 1, 1, '[person] was christened as an adult' + _S),
    (12, 0, 'Confirmation', 'Confirmation', 'CONF', 0, 1, 1, '[person] was confirmed' + _S),
    (13, 0, 'First communion', 'First comm', 'FCOM', 0, 1, 1, '[person] received first communion' + _S),
    (14, 0, 'Ordination', 'Ordination', 'ORDN', 0, 1, 1, '[person] was ordained' + _S),
    (15, 0, 'Naturalization', 'Naturalization', 'NATU', 0, 1, 1, '[person] was naturalized' + _S),
    (16, 0, 'Emigration', 'Emigration', 'EMIG', 0, 1, 1, '[person] emigrated< [Date]>< from [Place:plain]>< [PlaceDetails]>.'),
    (17, 0, 'Immigration', 'Immigration', 'IMMI', 0, 1, 1, '[person] immigrated< [Date]>< to [Place:plain]>< [PlaceDetails]>.'),
    (18, 0, 'Census', 'Census', 'CENS', 0, 1, 1, '[person] appeared in the census' + _S),
    (19, 0, 'Probate', 'Probate', 'PROB', 0, 1, 1, '[person] had [person:hisher] estate probated' + _S),
    (20, 0, 'Will', 'Will', 'WILL', 0, 1, 1, '[person] signed a will' + _S),
    (21, 0, 'Graduation', 'Graduation', 'GRAD', 0, 1, 1, '[person] graduated' + _S),
    (22, 0, 'Retirement', 'Retirement', 'RETI', 0, 1, 1, '[person] retired' + _S),
    (23, 0, 'Description', 'Description', 'DSCR', 1, 1, 1, '[person] was described as [Desc]' + _S),
    (24, 0, 'Education', 'Education', 'EDUC', 1, 1, 1, '[person] was educated< [Desc]>' + _S),
    (25, 0, 'Nationality', 'Nationality', 'NATI', 1, 1, 1, '[person] was [Desc]' + _S),
    (26, 0, 'Occupation', 'Occupation', 'OCCU', 1, 1, 1, '[person] worked as [Desc:A]< [Date]>< [PlaceDetails]>< [Place]>.'),
    (27, 0, 'Property', 'Property', 'PROP', 1, 1, 1, '[person] owned [Desc]' + _S),
    (28, 0, 'Religion', 'Religion', 'RELI', 1, 1, 1, '[person] was [Desc]' + _S),
    (29, 0, 'Residence', 'Residence', 'RESI', 1, 1, 1, '[person] lived< [Desc]>< [PlaceDetails]>< [Place]>< [Date]>.'),
    (30, 0, 'Soc Sec No', 'SSN', 'SSN', 1, 0, 0, "[person] had Social Security Number [Desc]."),
    (31, 0, 'LDS Baptism', 'LDS Bapt', 'BAPL', 0, 1, 1, '[person] was baptized into the LDS Church' + _S),
    (32, 0, 'LDS Endowment', 'LDS Endow', 'ENDL', 0, 1, 1, '[person] was endowed' + _S),
    (33, 0, 'LDS Seal to parents', 'LDS SealPar', 'SLGC', 0, 1, 1, '[person] was sealed to [person:hisher] parents' + _S),
    (34, 0, 'Ancestral File Number', 'AFN', 'AFN', 1, 0, 0, '[person] has Ancestral File Number [Desc].'),
    (35, 0, 'Reference No', 'Ref #', 'REFN', 1, 0, 0, '[person] has reference number [Desc].'),
    (36, 0, 'Caste', 'Caste', 'CAST', 1, 1, 1, '[person] was associated with [Desc]' + _S),
    (37, 0, 'Title (Nobility)', 'Title', 'TITL', 1, 1, 1, '[person] held the title of [Desc]' + _S),
    (38, 0, 'LDS Confirmation', 'LDS Conf', 'CONL', 0, 1, 1, '[person] was confirmed a member of the LDS Church' + _S),
    (39, 0, 'LDS Initiatory', 'LDS Init', 'WAC', 0, 1, 1, '[person] received LDS initiatory' + _S),
    (300, 1, 'Marriage', 'Marriage', 'MARR', 0, 1, 1, '[couple] <#Couple#was|were> married' + _S),
    (301, 1, 'Annulment', 'Annulment', 'ANUL', 0, 1, 1, '[couple] had their marriage annulled' + _S),
    (302, 1, 'Divorce', 'Divorce', 'DIV', 0, 1, 1, '[couple] <#Couple#was|were> divorced' + _S),
    (303, 1, 'Divorce filed', 'Div. filed', 'DIVF', 0, 1, 1, '[couple] filed for divorce' + _S),
    (304, 1, 'Engagement', 'Engagement', 'ENGA', 0, 1, 1, '[couple] <#Couple#was|were> engaged' + _S),
    (305, 1, 'Marriage Bann', 'Marr Bann', 'MARB', 0, 1, 1, '[couple] had marriage banns published' + _S),
    (306, 1, 'Marriage Contract', 'Marr Contract', 'MARC', 0, 1, 1, '[couple] signed a marriage contract' + _S),
    (307, 1, 'Marriage License', 'Marr Lic', 'MARL', 0, 1, 1, '[couple] obtained a marriage license' + _S),
    (308, 1, 'Marriage Settlement', 'Marr Settlement', 'MARS', 0, 1, 1, '[couple] made a marriage settlement' + _S),
    (309, 1, 'LDS Seal to spouse', 'LDS SealSp', 'SLGS', 0, 1, 1, '[couple] were sealed together' + _S),
    (310, 1, 'Residence (family)', 'Residence (fam)', 'RESI', 1, 1, 1, '[couple] lived< [Desc]>< [PlaceDetails]>< [Place]>< [Date]>.'),
    (311, 1, 'Census (family)', 'Census (fam)', 'CENS', 0, 1, 1, '[couple] appeared in the census' + _S),
    (312, 1, 'Separation', 'Separation', 'SEPA', 0, 1, 1, '[couple] separated' + _S),
    (999, 0, 'Miscellaneous', 'Misc', 'EVEN', 1, 1, 1, '[person]< [Desc]>' + _S),
    (1000, 0, 'Degree', 'Degree', 'DEGR', 1, 1, 1, '[person] received a< [Desc]> degree' + _S),
    (1001, 0, 'Military', 'Military', '_MILT', 1, 1, 1, '[person] served in the military< with the [Desc]>' + _S),
    (1002, 0, 'Mission', 'Mission', '_MISN', 1, 1, 1, '[person] served a mission' + _S),
    (1003, 0, 'Stillborn', 'Stillborn', '_STILL', 0, 1, 1, '[person] was stillborn' + _S),
    (1004, 0, 'Illness', 'Illness', '_ILLN', 1, 1, 1, '[person] was ill< with [Desc]>' + _S),
    (1005, 0, 'Living', 'Living', '_LIVING', 0, 1, 1, '[person] was living' + _S),
    (1006, 0, 'Election', 'Elected', '_ELEC', 1, 1, 1, '[person] was elected< as [Desc]>' + _S),
    (1007, 0, 'Excommunication', 'Excomm', '_EXCM', 0, 1, 1, '[person] was excommunicated' + _S),
    (1008, 0, 'Namesake', 'Namesake', '_NAMS', 1, 1, 0, '[person] was named after [Desc].'),
    (1009, 0, 'Alternate name', 'Alt. Name', '_AKA', 1, 1, 0, '[person] was also known as [Desc]< [Date]>.'),
    (1010, 0, 'DNA test', 'DNA', '_DNA', 1, 1, 0, '[person] had a DNA test performed< [Desc]>< [Date]>.'),
    (1011, 0, 'Physical description', 'Physical', '_PHYS', 1, 1, 0, '[person] was described as [Desc]< [Date]>.'),
]

# Roles for shared events: (fact type, role name, role type 0=principal 1=witness, sentence)
ROLES = [
    (1, 'Doctor', 1, '[ThisPerson] delivered [person]' + _S),
    (20, 'Heir', 1, '[ThisPerson] was named an heir in the will of [person]' + _S),
    (20, 'Executor', 1, '[ThisPerson] was named executor of the will of [person]' + _S),
    (18, 'Household member', 1, '[ThisPerson] appeared in the household of [person] in the census' + _S),
    (311, 'Household member', 1, '[ThisPerson] appeared in the census in the household of [couple]' + _S),
    (3, 'Godparent', 1, '[ThisPerson] was a godparent at the christening of [person]' + _S),
    (7, 'Godparent', 1, '[ThisPerson] was a godparent at the baptism of [person]' + _S),
    (300, 'Officiant', 1, '[ThisPerson] officiated at the marriage of [couple]' + _S),
    (4, 'Informant', 1, '[ThisPerson] was the informant for the burial of [person]' + _S),
    (2, 'Informant', 1, '[ThisPerson] reported the death of [person]' + _S),
]

FAN_TYPES = [  # name, role1, role2, sentence1, sentence2
    ('Friend', 'Friend', 'Friend', '[ThisPerson] was a friend of [person]< [Date]>.', ''),
    ('Neighbor', 'Neighbor', 'Neighbor', '[ThisPerson] was a neighbor of [person]< [Date]>< [Place]>.', ''),
    ('Godparent', 'Godparent', 'Godchild', '[ThisPerson] was the godparent of [person]< [Date]>.', '[ThisPerson] was the godchild of [person]< [Date]>.'),
    ('Employment', 'Employer', 'Employee', '[ThisPerson] employed [person]< [Date]>< [Place]>.', '[ThisPerson] worked for [person]< [Date]>< [Place]>.'),
    ('Teacher', 'Teacher', 'Student', '[ThisPerson] taught [person]< [Date]>.', '[ThisPerson] was a student of [person]< [Date]>.'),
    ('Guardian', 'Guardian', 'Ward', '[ThisPerson] was the guardian of [person]< [Date]>.', '[ThisPerson] was the ward of [person]< [Date]>.'),
    ('Business partner', 'Partner', 'Partner', '[ThisPerson] was in business with [person]< [Date]>< [Place]>.', ''),
    ('Fellow soldier', 'Soldier', 'Soldier', '[ThisPerson] served in the military with [person]< [Date]>.', ''),
    ('Classmate', 'Classmate', 'Classmate', '[ThisPerson] was a classmate of [person]< [Date]>.', ''),
    ('Clergy', 'Clergy', 'Parishioner', '[ThisPerson] was the minister of [person]< [Date]>.', '[ThisPerson] was a parishioner of [person]< [Date]>.'),
    ('DNA match', 'Match', 'Match', '[ThisPerson] shares DNA with [person].', ''),
]


def _tf(*fields):
    """Field-def XML for a source template: (type, name, display, hint, is_citation_detail)."""
    out = ['<Root><Fields>']
    for t, n, d, h, det in fields:
        out.append(f'<Field><FieldName>{n}</FieldName><DisplayName>{d}</DisplayName><Type>{t}</Type>'
                   f'<Hint>{h}</Hint><LongHint></LongHint><CitationField>{det}</CitationField></Field>')
    out.append('</Fields></Root>')
    return ''.join(out)


# Starter templates (our own wording). Users can import RootsMagic's full template library
# from rootsmagic.st or from any .rmtree file via Lists > Source Templates > Import.
SOURCE_TEMPLATES = [
    ('Book (basic)', 'A published book', 'Published sources',
     '[Author], <i>[Title]</i> ([PubPlace]: [Publisher], [PubDate])<, [Page]>.',
     '[Author:Surname], <i>[Title:Abbrev]</i><, [Page]>.',
     '[Author:Reverse]. <i>[Title]</i>. [PubPlace]: [Publisher], [PubDate].',
     _tf(('Name', 'Author', 'Author', 'e.g. John /Smith/', 'False'), ('Text', 'Title', 'Title', '', 'False'),
         ('Place', 'PubPlace', 'Publication place', '', 'False'), ('Text', 'Publisher', 'Publisher', '', 'False'),
         ('Date', 'PubDate', 'Publication date', '', 'False'), ('Text', 'Page', 'Page', 'page(s) cited', 'True'))),
    ('Census, U.S. Federal (basic)', 'U.S. federal population schedule', 'Census records',
     '[Year] U.S. census, [County] County, [State], population schedule<, [CivilDivision]>, <p. [Page]>, <dwelling [Dwelling]>, <family [Family]>, [Person]<; [Repository]>.',
     '[Year] U.S. census, [County] Co., [State], pop. sch.<, p. [Page]>, [Person].',
     'U.S. [State]. [County] County. [Year] U.S. census, population schedule.',
     _tf(('Text', 'Year', 'Census year', 'e.g. 1880', 'False'), ('Text', 'State', 'State', '', 'False'),
         ('Text', 'County', 'County', '', 'False'), ('Text', 'CivilDivision', 'Civil division', 'township, ward', 'True'),
         ('Text', 'Page', 'Page', '', 'True'), ('Text', 'Dwelling', 'Dwelling', '', 'True'),
         ('Text', 'Family', 'Family', '', 'True'), ('Name', 'Person', 'Person of interest', '', 'True'),
         ('Text', 'Repository', 'Repository / database', 'e.g. NARA microfilm', 'False'))),
    ('Vital record (certificate)', 'Birth, marriage or death certificate', 'Vital records',
     '[Jurisdiction], [RecordType]< no. [CertNo]><, [Person]>< ([EventDate])>, [Office]<, [Location]>.',
     '[Jurisdiction], [RecordType]< no. [CertNo]><, [Person]>.',
     '[Jurisdiction]. [RecordType]s. [Office]<, [Location]>.',
     _tf(('Text', 'Jurisdiction', 'Jurisdiction', 'e.g. Ohio Department of Health', 'False'),
         ('Text', 'RecordType', 'Record type', 'e.g. death certificate', 'False'), ('Text', 'Office', 'Issuing office', '', 'False'),
         ('Place', 'Location', 'Office location', '', 'False'), ('Text', 'CertNo', 'Certificate number', '', 'True'),
         ('Name', 'Person', 'Person', '', 'True'), ('Date', 'EventDate', 'Event date', '', 'True'))),
    ('Website (basic)', 'An online page', 'Online sources',
     '"[PageTitle]," <i>[Website]</i> ([URL] : accessed [AccessDate])<, [Item]>.',
     '"[PageTitle:Abbrev]," <i>[Website]</i><, [Item]>.',
     '<i>[Website]</i>. [URL] : [AccessDate].',
     _tf(('Text', 'Website', 'Website title', '', 'False'), ('Text', 'URL', 'URL', '', 'False'),
         ('Text', 'PageTitle', 'Page title', '', 'True'), ('Date', 'AccessDate', 'Access date', '', 'True'),
         ('Text', 'Item', 'Item of interest', '', 'True'))),
    ('Newspaper article', 'An item in a newspaper', 'Published sources',
     '"[Headline]," <i>[Newspaper]</i> ([NewsPlace]), [IssueDate]<, p. [Page]>< col. [Column]>.',
     '"[Headline:Abbrev]," <i>[Newspaper]</i>, [IssueDate]<, p. [Page]>.',
     '<i>[Newspaper]</i>. [NewsPlace].',
     _tf(('Text', 'Newspaper', 'Newspaper', '', 'False'), ('Place', 'NewsPlace', 'Place of publication', '', 'False'),
         ('Text', 'Headline', 'Headline', '', 'True'), ('Date', 'IssueDate', 'Issue date', '', 'True'),
         ('Text', 'Page', 'Page', '', 'True'), ('Text', 'Column', 'Column', '', 'True'))),
    ('Cemetery marker', 'A gravestone or monument', 'Cemetery records',
     '[Cemetery] ([CemPlace]), [Person] marker<, [Section]>; <photographed by [Photographer]>< [PhotoDate]>.',
     '[Cemetery], [Person] marker.',
     '[CemPlace]. [Cemetery]. Grave markers.',
     _tf(('Text', 'Cemetery', 'Cemetery', '', 'False'), ('Place', 'CemPlace', 'Cemetery location', '', 'False'),
         ('Name', 'Person', 'Person', '', 'True'), ('Text', 'Section', 'Section / plot', '', 'True'),
         ('Name', 'Photographer', 'Photographer', '', 'True'), ('Date', 'PhotoDate', 'Photo date', '', 'True'))),
    ('Church register', 'Parish or congregational register', 'Church records',
     '[Church] ([ChurchPlace]), "[Register]," [Entry]<, p. [Page]>.',
     '[Church], "[Register:Abbrev]," [Entry].',
     '[ChurchPlace]. [Church]. "[Register]."',
     _tf(('Text', 'Church', 'Church', '', 'False'), ('Place', 'ChurchPlace', 'Church location', '', 'False'),
         ('Text', 'Register', 'Register', 'e.g. Baptisms 1820-1860', 'False'), ('Text', 'Entry', 'Entry', 'person and date', 'True'),
         ('Text', 'Page', 'Page', '', 'True'))),
    ('Family Bible', 'Family Bible record', 'Family records',
     '[Family] Family Bible, <i>[BibleTitle]</i> ([PubPlace]: [Publisher], [PubDate]), "[Page]"; <owned by [Owner]>< ([OwnerPlace])>.',
     '[Family] Family Bible, "[Page]."',
     '[Family] Family Bible. <i>[BibleTitle]</i>. [PubPlace]: [Publisher], [PubDate].',
     _tf(('Text', 'Family', 'Family', '', 'False'), ('Text', 'BibleTitle', 'Bible title', '', 'False'),
         ('Place', 'PubPlace', 'Publication place', '', 'False'), ('Text', 'Publisher', 'Publisher', '', 'False'),
         ('Date', 'PubDate', 'Publication date', '', 'False'), ('Name', 'Owner', 'Current owner', '', 'False'),
         ('Place', 'OwnerPlace', 'Owner location', '', 'False'), ('Text', 'Page', 'Page / section', '', 'True'))),
    ('Interview', 'Oral interview', 'Personal knowledge',
     '[Informant] ([InfAddress]), interview by [Interviewer], [IntDate]<; [Item]>.',
     '[Informant:Surname] interview, [IntDate].',
     '[Informant:Reverse]. Interview. [IntDate].',
     _tf(('Name', 'Informant', 'Informant', '', 'False'), ('Place', 'InfAddress', 'Informant address', '', 'False'),
         ('Name', 'Interviewer', 'Interviewer', '', 'False'), ('Date', 'IntDate', 'Interview date', '', 'False'),
         ('Text', 'Item', 'Item of interest', '', 'True'))),
]

# Default app settings, stored as JSON in ConfigTable(RecType=DZ_CONFIG).
DZ_CONFIG = 1001
DEFAULT_SETTINGS = {
    'dateFormat': 'dmy', 'surnameCaps': False, 'nameFormat': 'given_surname',
    'showIds': True, 'theme': 'light', 'fontScale': 1.0, 'rootPersonId': 0,
    'preparer': {'name': '', 'address': '', 'email': '', 'phone': ''},
    'livingYears': 110, 'mediaFolder': '', 'backupFolder': '', 'exportFolder': '',
    'colorNames': ['', 'Red', 'Lime', 'Blue', 'Fuchsia', 'Yellow', 'Aqua', 'Silver', 'Maroon',
                   'Green', 'Navy', 'Purple', 'Brown', 'Teal', 'Gray', 'Orange', 'Pink',
                   'Chartreuse', 'Light blue', 'Lavender', 'Cream', 'Gold', 'Tan', 'Olive', 'White', 'Black', 'Violet', 'Coral'],
    'colorSetNames': ['Color set 1', 'Color set 2', 'Color set 3', 'Color set 4', 'Color set 5',
                      'Color set 6', 'Color set 7', 'Color set 8', 'Color set 9', 'Color set 10'],
    'activeColorSet': 0, 'showLds': False,
    'personListColumns': ['birth', 'death'],
    'webSearchProviders': [
        {'name': 'FamilySearch', 'url': 'https://www.familysearch.org/search/record/results?q.givenName={given}&q.surname={surname}&q.birthLikeDate.from={birthyear}'},
        {'name': 'Ancestry', 'url': 'https://www.ancestry.com/search/?name={given}_{surname}&birth={birthyear}'},
        {'name': 'FindAGrave', 'url': 'https://www.findagrave.com/memorial/search?firstname={given}&lastname={surname}&birthyear={birthyear}&deathyear={deathyear}'},
        {'name': 'Google', 'url': 'https://www.google.com/search?q=%22{given}+{surname}%22+{birthyear}'},
        {'name': 'MyHeritage', 'url': 'https://www.myheritage.com/research?formId=master&qname=Name+fn.{given}+ln.{surname}'},
    ],
}


def rmnocase(a, b):
    a, b = (a or '').casefold(), (b or '').casefold()
    return (a > b) - (a < b)


def utc_now():
    """Delphi TDateTime (days since 1899-12-30), the format of RM's UTCModDate."""
    return time.time() / 86400.0 + 25569.0


def unique_id():
    """36-hex GEDCOM _UID: 16 random bytes + 2-byte checksum (PAF algorithm)."""
    b = uuid.uuid4().bytes
    a = s = 0
    for x in b:
        a = (a + x) & 0xFF
        s = (s + a) & 0xFF
    return (b.hex() + '%02x%02x' % (a, s)).upper()


def connect(path):
    con = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    con.create_collation('RMNOCASE', rmnocase)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    return con


def create(path):
    if os.path.exists(path):
        raise FileExistsError(path)
    con = connect(path)
    con.executescript(SCHEMA)
    seed(con)
    return con


def upgrade(con):
    """Make an older/foreign file usable: add missing tables/indexes and our config row."""
    con.executescript(SCHEMA)
    if not con.execute('SELECT 1 FROM FactTypeTable LIMIT 1').fetchone():
        seed(con)


def seed(con):
    now = utc_now()
    with tx(con):
        for fid, own, name, abbr, tag, uv, ud, up, sent in FACT_TYPES:
            con.execute('INSERT OR IGNORE INTO FactTypeTable VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        (fid, own, name, abbr, tag, uv, ud, up, sent, 0, now))
        for i, (et, name, rt, sent) in enumerate(ROLES, 1):
            con.execute('INSERT OR IGNORE INTO RoleTable VALUES (?,?,?,?,?,?)', (i, name, et, rt, sent, now))
        for i, (name, r1, r2, s1, s2) in enumerate(FAN_TYPES, 1):
            con.execute('INSERT OR IGNORE INTO FANTypeTable VALUES (?,?,?,?,?,?,?)', (i, name, r1, r2, s1, s2, now))
        for i, (name, desc, cat, fn, sfn, bib, defs) in enumerate(SOURCE_TEMPLATES, 10001):
            con.execute('INSERT OR IGNORE INTO SourceTemplateTable VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (i, name, desc, 0, cat, fn, sfn, bib, defs, now))


class tx:
    """`with tx(con):` — BEGIN/COMMIT/ROLLBACK on an autocommit connection; nests via savepoints."""
    def __init__(self, con):
        self.con = con

    def __enter__(self):
        self.nested = self.con.in_transaction
        self.con.execute('SAVEPOINT sp' if self.nested else 'BEGIN')
        return self.con

    def __exit__(self, et, ev, tb):
        if self.nested:
            self.con.execute('ROLLBACK TO sp' if et else 'RELEASE sp')
        else:
            self.con.execute('ROLLBACK' if et else 'COMMIT')
        return False


def rows(con, sql, *args):
    return [dict(r) for r in con.execute(sql, args)]


def row(con, sql, *args):
    r = con.execute(sql, args).fetchone()
    return dict(r) if r else None


def insert(con, table, data):
    """Insert dict into table (only columns that exist). Returns rowid. Adds UTCModDate."""
    cols = table_columns(con, table)
    data = {k: v for k, v in data.items() if k in cols}
    if 'UTCModDate' in cols:
        data['UTCModDate'] = utc_now()
    keys = ','.join(data)
    cur = con.execute(f'INSERT INTO {table} ({keys}) VALUES ({",".join("?" * len(data))})', list(data.values()))
    return cur.lastrowid


def update(con, table, pk, pkval, data):
    cols = table_columns(con, table)
    data = {k: v for k, v in data.items() if k in cols and k != pk}
    if 'UTCModDate' in cols:
        data['UTCModDate'] = utc_now()
    if data:
        con.execute(f'UPDATE {table} SET {",".join(k + "=?" for k in data)} WHERE {pk}=?',
                    list(data.values()) + [pkval])


_cols = {}


def table_columns(con, table):
    key = (id(con), table)
    if key not in _cols:
        _cols[key] = [r[1] for r in con.execute(f'PRAGMA table_info({table})')]
    return _cols[key]


if __name__ == '__main__':
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), 't.rmtree')
    c = create(p)
    assert c.execute('SELECT Name FROM FactTypeTable WHERE FactTypeID=300').fetchone()[0] == 'Marriage'
    assert c.execute("SELECT COUNT(*) FROM FactTypeTable WHERE Name='birth'").fetchone()[0] == 1  # RMNOCASE
    assert len(unique_id()) == 36
    pid = insert(c, 'PersonTable', {'Sex': 0, 'Bogus': 1})
    update(c, 'PersonTable', 'PersonID', pid, {'Sex': 1})
    assert row(c, 'SELECT Sex FROM PersonTable WHERE PersonID=?', pid)['Sex'] == 1
    try:
        with tx(c):
            insert(c, 'PersonTable', {'Sex': 0})
            raise RuntimeError
    except RuntimeError:
        pass
    assert c.execute('SELECT COUNT(*) FROM PersonTable').fetchone()[0] == 1
    print('db ok')
