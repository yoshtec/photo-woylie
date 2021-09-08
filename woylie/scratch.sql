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
