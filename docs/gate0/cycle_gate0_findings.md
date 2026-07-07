# Gate 0 findings — Option A: cycle-hire journey archive

Inventory: see [cycle_file_inventory.csv](cycle_file_inventory.csv) (482 objects, 16.4 GB).

## Sample measurements

| file | kind | rows | MB | rows/MB |
|---|---|---:|---:|---:|
| 01aJourneyDataExtract10Jan16-23Jan16.csv | csv | 284,587 | 34.5 | 8,261 |
| 143JourneyDataExtract02Jan2019-08Jan2019.csv | csv | 142,413 | 17.3 | 8,242 |
| 299JourneyDataExtract05Jan2022-11Jan2022.csv | csv | 134,383 | 16.5 | 8,120 |
| 435JourneyDataExtract01Jan2026-15Jan2026.csv | csv | 234,788 | 39.0 | 6,013 |
| 49JourneyDataExtract15Mar2017-21Mar2017.xlsx | xlsx | 174,598 | 10.9 | 15,960 |
| cyclehireusagestats-2013.zip | zip | 8,042,370 | 183.1 | 43,915 |

## Schemas per era (verbatim column names)

**01aJourneyDataExtract10Jan16-23Jan16.csv**
```
Rental Id, Duration, Bike Id, End Date, EndStation Id, EndStation Name, Start Date, StartStation Id, StartStation Name
```

**143JourneyDataExtract02Jan2019-08Jan2019.csv**
```
Rental Id, Duration, Bike Id, End Date, EndStation Id, EndStation Name, Start Date, StartStation Id, StartStation Name
```

**299JourneyDataExtract05Jan2022-11Jan2022.csv**
```
Rental Id, Duration, Bike Id, End Date, EndStation Id, EndStation Name, Start Date, StartStation Id, StartStation Name
```

**435JourneyDataExtract01Jan2026-15Jan2026.csv**
```
Number, Start date, Start station number, Start station, End date, End station number, End station, Bike number, Bike model, Total duration, Total duration (ms)
```

**49JourneyDataExtract15Mar2017-21Mar2017.xlsx**
```
Rental Id, Duration, Bike Id, End Date, EndStation Id, EndStation Name, Start Date, StartStation Id, StartStation Name
```

**cyclehireusagestats-2013.zip**
```
Rental Id, Duration, Bike Id, End Date, EndStation Id, EndStation Name, Start Date, StartStation Id, StartStation Name
```
(zip: 14 member CSVs, 1 distinct header variants)

## Full-history row estimate

- CSV/xlsx era rate: 9,319 rows/MB over 15,315 MB → ~143M rows
- zip era rate (compressed): 43,915 rows/MB over 1,065 MB → ~47M rows
- **Estimated total: ~189M rows**
