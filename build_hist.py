"""One-off: turn the 2026-08-01 open-slip set into slips.py's file format."""
import json
MMA="MMA"; BOX="BOX"; WNBA="WNBA"; PROP="PROP"

def L(lab, price, sport, **kw):
    d = {"lab": lab, "price": price, "sport": sport}; d.update(kw); return d

MR = "MEDIC-RODRIGUEZ"; ST = "STIRLING"

T14 = [L("Cepo ML",-335,MMA),L("Rakic ML",-390,MMA),L("Pattinson ML",-380,BOX),
 L("Stirling by points",105,PROP,mkt=ST,out="Stirling by points",implies="Stirling ML"),
 L("Barney-Smith ML",-650,BOX),
 L("Rodriguez R4+",1100,PROP,mkt=MR,out="Rodriguez R4+"),
 L("Kaleiopu ML",-3000,BOX),L("Cabrera ML",-5000,BOX),L("Guzman ML",-1600,BOX),
 L("Capetillo ML",-4500,BOX),L("Iriarte ML",-5000,BOX),L("Conwell ML",-650,BOX),
 L("Curiel ML",-1300,BOX),L("Muratalla ML",-1300,BOX)]

T14b = [L("Cepo ML",-335,MMA),L("Rakic ML",-390,MMA),
 L("Stirling ML",-300,MMA,mkt=ST,out="Stirling ML"),
 L("Rodriguez R4+",1100,PROP,mkt=MR,out="Rodriguez R4+"),
 L("Pattinson ML",-380,BOX),L("Barney-Smith ML",-650,BOX),L("Kaleiopu ML",-3000,BOX),
 L("Cabrera ML",-5000,BOX),L("Guzman ML",-1600,BOX),L("Capetillo ML",-4500,BOX),
 L("Iriarte ML",-5000,BOX),L("Conwell ML",-650,BOX),L("Curiel ML",-1300,BOX),
 L("Muratalla ML",-1300,BOX)]

T24 = [L("Luciano ML",-313,MMA),L("Leka ML",-273,MMA),L("Milosevic ML",-455,MMA),
 L("Rebecki ML",-634,MMA),L("Oliveira ML",-361,MMA),L("Cepo ML",-331,MMA),
 L("Rakic ML",-361,MMA),L("Pattinson ML",-352,BOX),
 L("Stirling ML",-300,MMA,mkt=ST,out="Stirling ML"),
 L("Medic ML",-370,MMA,mkt=MR,out="Medic ML"),
 L("Barney-Smith ML",-579,BOX),L("Kaleiopu ML",-1981,BOX),L("Cabrera ML",-2703,BOX),
 L("Guzman ML",-1247,BOX),L("Capetillo ML",-2552,BOX),L("Iriarte ML",-2703,BOX),
 L("Conwell ML",-579,BOX),L("Curiel ML",-1055,BOX),L("Muratalla ML",-1055,BOX),
 L("Wings ML",-530,WNBA),L("Valkyries ML",-619,WNBA),L("Walsh ML",-538,BOX),
 L("Shields ML",-1981,BOX),L("Serrano ML",-1482,BOX)]

T16a = [L("Lynx ML",-750,WNBA),L("Magomedov ML",-3000,MMA),L("Nurmagomedov ML",-500,MMA),
 L("Dream ML",-750,WNBA),L("Luciano ML",-350,MMA),L("Milosevic ML",-550,MMA),
 L("Kaleiopu ML",-3000,BOX),L("Rebecki ML",-650,MMA),L("Oliveira ML",-355,MMA),
 L("Cepo ML",-375,MMA),L("Rakic ML",-355,MMA),
 L("Stirling ML",-350,MMA,mkt=ST,out="Stirling ML"),
 L("Medic ML",-400,MMA,mkt=MR,out="Medic ML"),
 L("Conwell ML",-600,BOX),L("Curiel ML",-1300,BOX),L("Muratalla ML",-1600,BOX)]

T16b = [L("Lynx ML",-770,WNBA),L("Dream ML",-850,WNBA),L("Luciano ML",-325,MMA),
 L("Milosevic ML",-500,MMA),L("Cairns ML",-550,BOX),L("Barney-Smith ML",-700,BOX),
 L("Fail ML",-1200,BOX),L("Kaleiopu ML",-2500,BOX),L("Rebecki ML",-700,MMA),
 L("Oliveira ML",-345,MMA),L("Cepo ML",-355,MMA),L("Rakic ML",-355,MMA),
 L("Medic ML",-395,MMA,mkt=MR,out="Medic ML"),
 L("Conwell ML",-550,BOX),L("Curiel ML",-1200,BOX),L("Muratalla ML",-1400,BOX)]

J = {"as_of": "2026-08-01",
     "note": ("The five slips open on the morning of 2026-08-01. Kept because "
              "this is the set that all died at once when Cepo lost, and it is "
              "the regression case for the cross-slip maths."),
     "slips": [
       {"name":"14-leg +9040","book":"FanDuel","price":9040,"legs":T14},
       {"name":"14-leg +5751","book":"FanDuel","price":5751,"legs":T14b},
       {"name":"24-leg +4433","book":"FanDuel","price":4433,"legs":T24},
       {"name":"16-leg +1188","book":"FanDuel","price":1188,"legs":T16a},
       {"name":"16-pick +1155","book":"other","price":1155,"legs":T16b}]}
open("/root/parlay/slips_2026-08-01.json","w").write(json.dumps(J, indent=1))
print("wrote slips_2026-08-01.json")
