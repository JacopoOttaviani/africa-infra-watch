[out:json][timeout:180];
(way["highway"="construction"](-36,-18,39,52);
 way["highway"="proposed"](-36,-18,39,52););
out count;
convert way ::id=id(), hw=t["highway"], c=t["construction"], p=t["proposed"], name=t["name"], rw=t["railway"], ae=t["aeroway"], len=length(), ::geom=center(geom());
out geom;
