select *
 from exif
where Face1Position not null
order by make, Model;

select count(FileName) as C, Make, Model, SerialNumber
from exif
group by Make, Model, SerialNumber
order by C;

select count(FileName) as c, make, model, Left(ThumbnailImage,10)
from exif
group by Make, Model;


select count(*),  sum(length(ThumbnailImage)) * 8 / 1024 / 1024  as Thsizemb , sum(length(PreviewImage)) * 8 / 1024 / 1024  as Psizemb  from exif where ThumbnailImage is not NULL;

select * FROM exif where MPImage2 not null;


select count(FileName) as C, Make, Model, SerialNumber
from exif
where GPSLatitude is not null
group by Make, Model, SerialNumber;


select *
from exif
where Model = 'iPhone 8 Plus';



create Table owner(
	"Owner" TEXT
	Make TEXT
	Model TEXT
	"FromDate" TEXT -- time in UTC
	"ToDate" TEXT
	)



-- finding the smallest
select abs(strftime('%s','2015-11-05T09:47:56+00:00') - strftime('%s',utc_time)) as delta_sec, file_hash, GPSPosition, GPSLatitude, GPSLongitude
from exif
where GPSPosition not NULL
order by delta_sec;


select e1.file_hash, min(abs(strftime('%s',e1.utc_time) - strftime('%s',e2.utc_time))) as delta_sec, e2.file_hash, e2.GPSPosition, e2.GPSLatitude, e2.GPSLongitude
from exif  as e1, exif as e2
where e2.GPSPosition not NULL and e1.GPSPosition is null
limit 1000;



select min(abs(strftime('%s','2015-11-05T09:47:56+00:00') - strftime('%s',utc_time))) as delta_sec, file_hash, GPSPosition, GPSLatitude, GPSLongitude
from exif
where GPSPosition not NULL;




select
	e1.file_hash as f1,
	e2.file_hash as f2,
	abs(strftime('%s',e1.utc_time) - strftime('%s',e2.utc_time)) as u_delta
from
	exif  as e1,
	exif as e2
where e2.GPSPosition is null and e1. GPSPosition not null

order by u_delta
limit 1000;
