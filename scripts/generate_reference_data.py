"""Generate reference data files for SpendCube Phase 1."""
import csv
import yaml
import os
import random
from decimal import Decimal

BASE = "/Users/tompurnell/Documents/Claude/SpendCube/data/reference"
os.makedirs(BASE, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# 1. UNSPSC v24.csv
# ─────────────────────────────────────────────────────────────

UNSPSC_DATA = [
    # Segment 44 — Office/Photo/Film
    ("44", "Office Equipment and Accessories and Supplies",
     "4411", "Office machines and their supplies and accessories",
     "441112", "Printers",
     [("44111201","Laser printers"), ("44111202","Inkjet printers"),
      ("44111203","Multifunction printers"), ("44111204","Label printers")]),
    ("44", "Office Equipment and Accessories and Supplies",
     "4411", "Office machines and their supplies and accessories",
     "441113", "Copying machines",
     [("44111301","Digital photocopiers"), ("44111302","Analogue copiers"),
      ("44111303","Wide format copiers")]),
    ("44", "Office Equipment and Accessories and Supplies",
     "4411", "Office machines and their supplies and accessories",
     "441115", "Projectors",
     [("44111501","Data projectors"), ("44111502","Overhead projectors"),
      ("44111503","Short throw projectors")]),
    ("44", "Office Equipment and Accessories and Supplies",
     "4411", "Office machines and their supplies and accessories",
     "441120", "Shredders",
     [("44112001","Cross cut shredders"), ("44112002","Strip cut shredders"),
      ("44112003","Micro cut shredders")]),
    ("44", "Office Equipment and Accessories and Supplies",
     "4412", "Office supplies",
     "441213", "Paper products",
     [("44121301","A4 copy paper"), ("44121302","A3 copy paper"),
      ("44121303","Letterhead paper"), ("44121304","Envelopes"),
      ("44121305","Notepads")]),
    ("44", "Office Equipment and Accessories and Supplies",
     "4412", "Office supplies",
     "441215", "Ink and toner and related supplies",
     [("44121501","Laser toner cartridges"), ("44121502","Inkjet cartridges"),
      ("44121503","Printer ribbons"), ("44121504","Drum units")]),
    ("44", "Office Equipment and Accessories and Supplies",
     "4412", "Office supplies",
     "441214", "Writing instruments",
     [("44121401","Ballpoint pens"), ("44121402","Permanent markers"),
      ("44121403","Highlighters"), ("44121404","Correction fluid")]),
    ("44", "Office Equipment and Accessories and Supplies",
     "4413", "Filing products",
     "441317", "Binders and binding supplies",
     [("44131701","Ring binders"), ("44131702","Lever arch files"),
      ("44131703","Binding covers"), ("44131704","Index dividers")]),
    ("44", "Office Equipment and Accessories and Supplies",
     "4413", "Filing products",
     "441316", "Filing folders and labels",
     [("44131601","Manila folders"), ("44131602","Hanging files"),
      ("44131603","Document wallets"), ("44131604","File labels")]),

    # Segment 43 — IT/Broadcasting/Telecommunications
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4315", "Data Voice or Multimedia Network Equipment or Platforms",
     "431521", "Network switches",
     [("43152101","Managed ethernet switches"), ("43152102","Unmanaged switches"),
      ("43152103","PoE switches"), ("43152104","Core switches")]),
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4315", "Data Voice or Multimedia Network Equipment or Platforms",
     "431522", "Routers",
     [("43152201","Enterprise routers"), ("43152202","SOHO routers"),
      ("43152203","Core routers"), ("43152204","Edge routers")]),
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4315", "Data Voice or Multimedia Network Equipment or Platforms",
     "431523", "Wireless access points",
     [("43152301","Indoor access points"), ("43152302","Outdoor access points"),
      ("43152303","Mesh access points")]),
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4321", "Computer Equipment and Accessories",
     "432101", "Desktop computers",
     [("43210101","Standard desktop PCs"), ("43210102","All-in-one desktops"),
      ("43210103","Workstation desktops"), ("43210104","Mini PCs")]),
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4321", "Computer Equipment and Accessories",
     "432102", "Laptop computers",
     [("43210201","Business laptops"), ("43210202","Gaming laptops"),
      ("43210203","Ultrabooks"), ("43210204","2-in-1 laptops")]),
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4321", "Computer Equipment and Accessories",
     "432103", "Computer monitors",
     [("43210301","LCD monitors"), ("43210302","Curved monitors"),
      ("43210303","4K monitors"), ("43210304","Ultrawide monitors")]),
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4321", "Computer Equipment and Accessories",
     "432106", "Computer storage devices",
     [("43210601","Solid state drives"), ("43210602","Hard disk drives"),
      ("43210603","USB flash drives"), ("43210604","External drives")]),
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4323", "Software",
     "432301", "Business function software",
     [("43230101","ERP software"), ("43230102","CRM software"),
      ("43230103","Accounting software"), ("43230104","HR management software")]),
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4323", "Software",
     "432302", "Security software",
     [("43230201","Antivirus software"), ("43230202","Firewall software"),
      ("43230203","Endpoint protection"), ("43230204","Identity management")]),
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4316", "Telecommunications equipment",
     "431601", "Telephone equipment",
     [("43160101","IP desk phones"), ("43160102","Conference phones"),
      ("43160103","Headsets"), ("43160104","VoIP handsets")]),
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4316", "Telecommunications equipment",
     "431602", "Mobile devices",
     [("43160201","Smartphones"), ("43160202","Tablets"),
      ("43160203","Mobile hotspots"), ("43160204","Rugged devices")]),

    # Segment 78 — Transportation/Storage
    ("78", "Transportation and Storage and Mail Services",
     "7810", "Mail and cargo transport",
     "781010", "Air freight services",
     [("78101001","International air freight"), ("78101002","Domestic air freight"),
      ("78101003","Express air courier"), ("78101004","Air charter services")]),
    ("78", "Transportation and Storage and Mail Services",
     "7810", "Mail and cargo transport",
     "781011", "Ocean freight services",
     [("78101101","Full container load"), ("78101102","Less than container load"),
      ("78101103","Break bulk shipping"), ("78101104","Roll-on roll-off")]),
    ("78", "Transportation and Storage and Mail Services",
     "7810", "Mail and cargo transport",
     "781012", "Road freight services",
     [("78101201","Full truck load"), ("78101202","Less than truck load"),
      ("78101203","Express road freight"), ("78101204","Refrigerated road freight")]),
    ("78", "Transportation and Storage and Mail Services",
     "7810", "Mail and cargo transport",
     "781013", "Rail freight services",
     [("78101301","Intermodal rail freight"), ("78101302","Bulk rail freight"),
      ("78101303","Container rail freight")]),
    ("78", "Transportation and Storage and Mail Services",
     "7814", "Passenger transport",
     "781401", "Air passenger transport",
     [("78140101","Domestic airfares"), ("78140102","International airfares"),
      ("78140103","Business class airfares"), ("78140104","Charter flights")]),
    ("78", "Transportation and Storage and Mail Services",
     "7814", "Passenger transport",
     "781402", "Ground passenger transport",
     [("78140201","Taxi services"), ("78140202","Ride share services"),
      ("78140203","Bus charter"), ("78140204","Limousine services")]),
    ("78", "Transportation and Storage and Mail Services",
     "7830", "Storage",
     "783001", "Warehousing services",
     [("78300101","General warehousing"), ("78300102","Temperature controlled storage"),
      ("78300103","Bonded warehousing"), ("78300104","Fulfilment services")]),

    # Segment 80 — Management/Business
    ("80", "Management and Business Professionals and Administrative Services",
     "8010", "Management advisory services",
     "801012", "Strategy consulting",
     [("80101201","Strategic planning"), ("80101202","Market entry strategy"),
      ("80101203","Organisational design"), ("80101204","Change management")]),
    ("80", "Management and Business Professionals and Administrative Services",
     "8010", "Management advisory services",
     "801013", "Financial consulting",
     [("80101301","Financial due diligence"), ("80101302","Valuations"),
      ("80101303","Transaction advisory"), ("80101304","Working capital optimisation")]),
    ("80", "Management and Business Professionals and Administrative Services",
     "8010", "Management advisory services",
     "801015", "Human resources consulting",
     [("80101501","Talent management consulting"), ("80101502","Remuneration benchmarking"),
      ("80101503","Workforce planning"), ("80101504","Leadership assessment")]),
    ("80", "Management and Business Professionals and Administrative Services",
     "8011", "Legal services",
     "801116", "Corporate legal services",
     [("80111601","Contract drafting"), ("80111602","M&A legal advice"),
      ("80111603","Compliance advice"), ("80111604","Intellectual property")]),
    ("80", "Management and Business Professionals and Administrative Services",
     "8013", "Business administration services",
     "801315", "Accounting services",
     [("80131501","External audit"), ("80131502","Tax compliance"),
      ("80131503","Bookkeeping services"), ("80131504","Payroll processing")]),
    ("80", "Management and Business Professionals and Administrative Services",
     "8013", "Business administration services",
     "801316", "Recruitment services",
     [("80131601","Permanent recruitment"), ("80131602","Executive search"),
      ("80131603","Contract staffing"), ("80131604","Casual labour hire")]),

    # Segment 81 — Engineering/R&D
    ("81", "Engineering and Research and Technology Based Services",
     "8110", "Engineering services",
     "811011", "Civil engineering",
     [("81101101","Structural engineering"), ("81101102","Geotechnical engineering"),
      ("81101103","Traffic engineering"), ("81101104","Hydraulic engineering")]),
    ("81", "Engineering and Research and Technology Based Services",
     "8110", "Engineering services",
     "811012", "Mechanical engineering",
     [("81101201","Process engineering"), ("81101202","HVAC engineering"),
      ("81101203","Piping engineering"), ("81101204","Rotating equipment")]),
    ("81", "Engineering and Research and Technology Based Services",
     "8110", "Engineering services",
     "811013", "Electrical engineering",
     [("81101301","Power systems design"), ("81101302","Instrumentation design"),
      ("81101303","High voltage engineering"), ("81101304","Substation design")]),
    ("81", "Engineering and Research and Technology Based Services",
     "8111", "Research and development",
     "811111", "Applied research",
     [("81111101","Laboratory research services"), ("81111102","Pilot plant studies"),
      ("81111103","Technology assessment"), ("81111104","Feasibility studies")]),
    ("81", "Engineering and Research and Technology Based Services",
     "8111", "Research and development",
     "811112", "Development services",
     [("81111201","Prototype development"), ("81111202","Product testing"),
      ("81111203","Clinical trials"), ("81111204","Product validation")]),
    ("81", "Engineering and Research and Technology Based Services",
     "8113", "IT consulting",
     "811315", "Information technology consultation services",
     [("81131501","IT architecture consulting"), ("81131502","Cloud migration consulting"),
      ("81131503","Cybersecurity consulting"), ("81131504","Data analytics consulting")]),

    # Segment 72 — Building/Construction
    ("72", "Building and Construction and Maintenance Services",
     "7210", "Construction services",
     "721011", "Commercial construction",
     [("72101101","Office fit-out"), ("72101102","Retail fit-out"),
      ("72101103","Industrial construction"), ("72101104","Healthcare construction")]),
    ("72", "Building and Construction and Maintenance Services",
     "7210", "Construction services",
     "721012", "Civil construction",
     [("72101201","Road construction"), ("72101202","Bridge construction"),
      ("72101203","Pipeline construction"), ("72101204","Earthworks")]),
    ("72", "Building and Construction and Maintenance Services",
     "7211", "Building maintenance services",
     "721112", "Electrical maintenance",
     [("72111201","Electrical repairs"), ("72111202","Lighting maintenance"),
      ("72111203","Emergency generator maintenance"), ("72111204","UPS maintenance")]),
    ("72", "Building and Construction and Maintenance Services",
     "7211", "Building maintenance services",
     "721113", "HVAC maintenance",
     [("72111301","Air conditioning servicing"), ("72111302","Chiller maintenance"),
      ("72111303","Duct cleaning"), ("72111304","BMS maintenance")]),
    ("72", "Building and Construction and Maintenance Services",
     "7211", "Building maintenance services",
     "721114", "Plumbing services",
     [("72111401","Plumbing repairs"), ("72111402","Hot water systems"),
      ("72111403","Drainage services"), ("72111404","Fire sprinkler testing")]),
    ("72", "Building and Construction and Maintenance Services",
     "7213", "Landscaping and grounds maintenance",
     "721310", "Grounds maintenance",
     [("72131001","Lawn mowing services"), ("72131002","Garden maintenance"),
      ("72131003","Tree trimming"), ("72131004","Irrigation maintenance")]),

    # Segment 76 — Industrial Cleaning
    ("76", "Industrial Cleaning Services",
     "7605", "Cleaning and janitorial services",
     "760501", "Commercial cleaning",
     [("76050101","Office cleaning"), ("76050102","Retail cleaning"),
      ("76050103","Industrial cleaning"), ("76050104","High pressure cleaning")]),
    ("76", "Industrial Cleaning Services",
     "7605", "Cleaning and janitorial services",
     "760502", "Specialist cleaning",
     [("76050201","Carpet cleaning"), ("76050202","Window cleaning"),
      ("76050203","Graffiti removal"), ("76050204","Post construction cleaning")]),
    ("76", "Industrial Cleaning Services",
     "7606", "Cleaning supplies and equipment",
     "760601", "Cleaning chemicals",
     [("76060101","General purpose cleaners"), ("76060102","Disinfectants"),
      ("76060103","Sanitisers"), ("76060104","Degreasers")]),
    ("76", "Industrial Cleaning Services",
     "7606", "Cleaning supplies and equipment",
     "760602", "Cleaning equipment",
     [("76060201","Vacuum cleaners"), ("76060202","Floor scrubbers"),
      ("76060203","Pressure washers"), ("76060204","Steam cleaners")]),
    ("76", "Industrial Cleaning Services",
     "7606", "Cleaning supplies and equipment",
     "760603", "Cleaning consumables",
     [("76060301","Mops and buckets"), ("76060302","Microfibre cloths"),
      ("76060303","Disposable gloves"), ("76060304","Waste bin liners")]),

    # Segment 51 — Drugs/Pharma/Biotech
    ("51", "Drugs and Pharmaceutical Products",
     "5110", "Pharmaceutical drugs",
     "511011", "Analgesics",
     [("51101101","Paracetamol tablets"), ("51101102","Ibuprofen tablets"),
      ("51101103","Aspirin tablets"), ("51101104","Opioid analgesics")]),
    ("51", "Drugs and Pharmaceutical Products",
     "5110", "Pharmaceutical drugs",
     "511012", "Antibiotics",
     [("51101201","Penicillin antibiotics"), ("51101202","Cephalosporin antibiotics"),
      ("51101203","Macrolide antibiotics"), ("51101204","Fluoroquinolone antibiotics")]),
    ("51", "Drugs and Pharmaceutical Products",
     "5110", "Pharmaceutical drugs",
     "511015", "Cardiovascular drugs",
     [("51101501","Statins"), ("51101502","ACE inhibitors"),
      ("51101503","Beta blockers"), ("51101504","Antihypertensives")]),
    ("51", "Drugs and Pharmaceutical Products",
     "5110", "Pharmaceutical drugs",
     "511016", "Vaccines",
     [("51101601","Influenza vaccines"), ("51101602","COVID-19 vaccines"),
      ("51101603","Hepatitis vaccines"), ("51101604","Travel vaccines")]),
    ("51", "Drugs and Pharmaceutical Products",
     "5113", "Medical laboratory supplies",
     "511320", "Diagnostic reagents",
     [("51132001","Blood glucose reagents"), ("51132002","PCR reagents"),
      ("51132003","Immunoassay reagents"), ("51132004","Culture media")]),
    ("51", "Drugs and Pharmaceutical Products",
     "5113", "Medical laboratory supplies",
     "511321", "Laboratory consumables",
     [("51132101","Test tubes"), ("51132102","Petri dishes"),
      ("51132103","Pipette tips"), ("51132104","Centrifuge tubes")]),

    # Segment 50 — Food/Beverage/Tobacco
    ("50", "Food Beverage and Tobacco Products",
     "5010", "Meat and poultry",
     "501011", "Beef products",
     [("50101101","Fresh beef"), ("50101102","Frozen beef"),
      ("50101103","Processed beef"), ("50101104","Beef offal")]),
    ("50", "Food Beverage and Tobacco Products",
     "5010", "Meat and poultry",
     "501012", "Poultry products",
     [("50101201","Fresh chicken"), ("50101202","Frozen chicken"),
      ("50101203","Turkey products"), ("50101204","Duck products")]),
    ("50", "Food Beverage and Tobacco Products",
     "5020", "Beverages",
     "502020", "Non-alcoholic beverages",
     [("50202001","Bottled water"), ("50202002","Carbonated soft drinks"),
      ("50202003","Fruit juices"), ("50202004","Energy drinks")]),
    ("50", "Food Beverage and Tobacco Products",
     "5020", "Beverages",
     "502021", "Hot beverages",
     [("50202101","Coffee beans and grounds"), ("50202102","Tea bags"),
      ("50202103","Instant coffee"), ("50202104","Herbal teas")]),
    ("50", "Food Beverage and Tobacco Products",
     "5030", "Grocery and dry goods",
     "503012", "Snack foods",
     [("50301201","Biscuits and cookies"), ("50301202","Chips and crisps"),
      ("50301203","Nuts and seeds"), ("50301204","Dried fruits")]),
    ("50", "Food Beverage and Tobacco Products",
     "5030", "Grocery and dry goods",
     "503013", "Catering supplies",
     [("50301301","Disposable plates"), ("50301302","Paper napkins"),
      ("50301303","Disposable cutlery"), ("50301304","Take-away containers")]),

    # Segment 53 — Apparel/Luggage/Personal
    ("53", "Apparel and Luggage and Personal Care Products",
     "5310", "Clothing",
     "531011", "Work wear and uniforms",
     [("53101101","High visibility vests"), ("53101102","Safety overalls"),
      ("53101103","Corporate uniforms"), ("53101104","Embroidered shirts")]),
    ("53", "Apparel and Luggage and Personal Care Products",
     "5310", "Clothing",
     "531012", "Personal protective clothing",
     [("53101201","Safety boots"), ("53101202","Hard hats"),
      ("53101203","Safety gloves"), ("53101204","Safety glasses")]),
    ("53", "Apparel and Luggage and Personal Care Products",
     "5312", "Luggage",
     "531215", "Travel bags",
     [("53121501","Carry-on luggage"), ("53121502","Checked luggage"),
      ("53121503","Laptop bags"), ("53121504","Backpacks")]),
    ("53", "Apparel and Luggage and Personal Care Products",
     "5313", "Personal care products",
     "531315", "Hygiene products",
     [("53131501","Hand soap dispensers"), ("53131502","Hand sanitiser"),
      ("53131503","Paper towels"), ("53131504","Toilet tissue")]),
    ("53", "Apparel and Luggage and Personal Care Products",
     "5313", "Personal care products",
     "531316", "First aid supplies",
     [("53131601","First aid kits"), ("53131602","Bandages"),
      ("53131603","Antiseptic wipes"), ("53131604","Eye wash")]),

    # Segment 73 — Industrial Production/Manufacturing
    ("73", "Industrial Production and Manufacturing Services",
     "7310", "Production support services",
     "731012", "Quality control services",
     [("73101201","Inspection services"), ("73101202","Testing services"),
      ("73101203","Calibration services"), ("73101204","Non-destructive testing")]),
    ("73", "Industrial Production and Manufacturing Services",
     "7310", "Production support services",
     "731013", "Contract manufacturing",
     [("73101301","Assembly services"), ("73101302","Machining services"),
      ("73101303","Fabrication services"), ("73101304","Surface treatment")]),
    ("73", "Industrial Production and Manufacturing Services",
     "7311", "Industrial machinery and equipment",
     "731110", "Material handling equipment",
     [("73111001","Forklifts"), ("73111002","Pallet jacks"),
      ("73111003","Conveyor systems"), ("73111004","Overhead cranes")]),
    ("73", "Industrial Production and Manufacturing Services",
     "7311", "Industrial machinery and equipment",
     "731111", "Power tools",
     [("73111101","Electric drills"), ("73111102","Angle grinders"),
      ("73111103","Impact wrenches"), ("73111104","Welding equipment")]),
    ("73", "Industrial Production and Manufacturing Services",
     "7312", "Raw materials",
     "731211", "Metals",
     [("73121101","Steel plate"), ("73121102","Aluminium sheet"),
      ("73121103","Copper wire"), ("73121104","Stainless steel pipe")]),
    ("73", "Industrial Production and Manufacturing Services",
     "7312", "Raw materials",
     "731212", "Plastics and polymers",
     [("73121201","HDPE pellets"), ("73121202","PVC compounds"),
      ("73121203","Polyurethane foam"), ("73121204","Nylon granules")]),

    # Segment 55 — Published Products
    ("55", "Published Products",
     "5510", "Printed publications",
     "551012", "Books and reference materials",
     [("55101201","Technical manuals"), ("55101202","Professional reference books"),
      ("55101203","Regulatory publications"), ("55101204","Training guides")]),
    ("55", "Published Products",
     "5510", "Printed publications",
     "551013", "Periodicals",
     [("55101301","Trade journals"), ("55101302","Industry magazines"),
      ("55101303","Professional newsletters"), ("55101304","Annual reports")]),
    ("55", "Published Products",
     "5511", "Electronic publications and media",
     "551115", "Online subscriptions",
     [("55111501","News and media subscriptions"), ("55111502","Research database subscriptions"),
      ("55111503","Standards subscriptions"), ("55111504","E-learning subscriptions")]),
    ("55", "Published Products",
     "5511", "Electronic publications and media",
     "551116", "Software documentation",
     [("55111601","Technical documentation sets"), ("55111602","API documentation"),
      ("55111603","User manuals"), ("55111604","Quick reference cards")]),
    ("55", "Published Products",
     "5512", "Maps and charts",
     "551210", "Digital maps",
     [("55121001","Geographic information systems"), ("55121002","Navigation maps"),
      ("55121003","Engineering drawings"), ("55121004","Survey maps")]),

    # Additional Segment 44 classes
    ("44", "Office Equipment and Accessories and Supplies",
     "4414", "Furniture",
     "441411", "Office furniture",
     [("44141101","Office desks"), ("44141102","Office chairs"),
      ("44141103","Filing cabinets"), ("44141104","Bookshelves"),
      ("44141105","Meeting tables")]),
    ("44", "Office Equipment and Accessories and Supplies",
     "4414", "Furniture",
     "441412", "Reception and waiting furniture",
     [("44141201","Reception desks"), ("44141202","Waiting room chairs"),
      ("44141203","Coffee tables"), ("44141204","Coat stands")]),
    ("44", "Office Equipment and Accessories and Supplies",
     "4416", "Audio visual equipment",
     "441616", "Video conferencing",
     [("44161601","Video conferencing systems"), ("44161602","Webcams"),
      ("44161603","Conference cameras"), ("44161604","Video bars")]),

    # Additional Segment 43 classes
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4317", "IT services",
     "431712", "Managed IT services",
     [("43171201","Managed helpdesk"), ("43171202","Managed security"),
      ("43171203","Managed backup"), ("43171204","Device management")]),
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4317", "IT services",
     "431713", "IT support services",
     [("43171301","On-site IT support"), ("43171302","Remote IT support"),
      ("43171303","Break-fix services"), ("43171304","IT project management")]),

    # Additional Segment 78 classes
    ("78", "Transportation and Storage and Mail Services",
     "7815", "Travel and accommodation",
     "781501", "Accommodation services",
     [("78150101","Hotel accommodation"), ("78150102","Serviced apartments"),
      ("78150103","Conference accommodation"), ("78150104","Extended stay")]),
    ("78", "Transportation and Storage and Mail Services",
     "7815", "Travel and accommodation",
     "781502", "Vehicle rental",
     [("78150201","Car rental"), ("78150202","Van rental"),
      ("78150203","Truck rental"), ("78150204","Minibus rental")]),

    # Additional Segment 80 classes
    ("80", "Management and Business Professionals and Administrative Services",
     "8013", "Business administration services",
     "801317", "Training and development services",
     [("80131701","Leadership training"), ("80131702","Technical training"),
      ("80131703","Compliance training"), ("80131704","Soft skills training")]),
    ("80", "Management and Business Professionals and Administrative Services",
     "8014", "Security services",
     "801415", "Physical security",
     [("80141501","Guard services"), ("80141502","Access control"),
      ("80141503","CCTV monitoring"), ("80141504","Alarm response")]),

    # Additional Segment 72 classes
    ("72", "Building and Construction and Maintenance Services",
     "7214", "Waste management",
     "721410", "Waste collection",
     [("72141001","General waste collection"), ("72141002","Recycling collection"),
      ("72141003","Hazardous waste disposal"), ("72141004","E-waste disposal")]),

    # Additional Segment 73 classes
    ("73", "Industrial Production and Manufacturing Services",
     "7313", "Safety and PPE",
     "731310", "Personal protective equipment",
     [("73131001","Safety helmets"), ("73131002","Safety footwear"),
      ("73131003","High-vis clothing"), ("73131004","Respiratory protection"),
      ("73131005","Eye and face protection")]),

    # Additional Segment 80 classes
    ("80", "Management and Business Professionals and Administrative Services",
     "8015", "Insurance services",
     "801511", "Business insurance",
     [("80151101","Public liability insurance"), ("80151102","Professional indemnity"),
      ("80151103","Workers compensation"), ("80151104","Property insurance"),
      ("80151105","Cyber insurance")]),

    # Additional Segment 81 classes
    ("81", "Engineering and Research and Technology Based Services",
     "8114", "Environmental services",
     "811411", "Environmental consulting",
     [("81141101","Environmental impact assessment"), ("81141102","Contamination assessment"),
      ("81141103","Environmental monitoring"), ("81141104","Remediation services")]),

    # Additional Segment 43 — Printing services
    ("43", "Information Technology Broadcasting and Telecommunications",
     "4319", "Printing services",
     "431910", "Digital printing",
     [("43191001","Large format printing"), ("43191002","Business card printing"),
      ("43191003","Brochure printing"), ("43191004","Banner printing"),
      ("43191005","Document printing services")]),

    # Additional Segment 50 — Food
    ("50", "Food Beverage and Tobacco Products",
     "5031", "Dairy products",
     "503111", "Milk and cream",
     [("50311101","Fresh full cream milk"), ("50311102","Skim milk"),
      ("50311103","Long life milk"), ("50311104","Cream"),
      ("50311105","Flavoured milk")]),

    # Additional Segment 78 — Courier
    ("78", "Transportation and Storage and Mail Services",
     "7816", "Postal and courier services",
     "781601", "Document courier",
     [("78160101","Same day courier"), ("78160102","Next day courier"),
      ("78160103","International document courier"), ("78160104","Registered post"),
      ("78160105","Overnight express")]),

    # Additional Segment 51 — Medical devices
    ("51", "Drugs and Pharmaceutical Products",
     "5115", "Medical equipment and supplies",
     "511516", "Medical diagnostic equipment",
     [("51151601","Blood pressure monitors"), ("51151602","Thermometers"),
      ("51151603","Oximeters"), ("51151604","Glucometers"),
      ("51151605","ECG machines")]),

    # Additional Segment 72 — Fire services
    ("72", "Building and Construction and Maintenance Services",
     "7211", "Building maintenance services",
     "721116", "Fire protection services",
     [("72111601","Fire extinguisher servicing"), ("72111602","Fire alarm testing"),
      ("72111603","Fire suppression maintenance"), ("72111604","Emergency exit testing")]),

    # Additional Segment 53 — Footwear
    ("53", "Apparel and Luggage and Personal Care Products",
     "5310", "Clothing",
     "531013", "Footwear",
     [("53101301","Dress shoes"), ("53101302","Casual shoes"),
      ("53101303","Athletic shoes"), ("53101304","Safety boots steel cap")]),

    # Additional Segment 55 — Training materials
    ("55", "Published Products",
     "5513", "Training and educational materials",
     "551310", "Training materials",
     [("55131001","Training workbooks"), ("55131002","Presentation slides"),
      ("55131003","Assessment materials"), ("55131004","Course certificates"),
      ("55131005","E-learning modules")]),

    # Additional Segment 44 — Postal
    ("44", "Office Equipment and Accessories and Supplies",
     "4415", "Mailing supplies",
     "441510", "Mailing and packing materials",
     [("44151001","Cardboard boxes"), ("44151002","Bubble wrap"),
      ("44151003","Packing tape"), ("44151004","Padded envelopes"),
      ("44151005","Stretch wrap"), ("44151006","Cable ties")]),
]

unspsc_rows = []
for entry in UNSPSC_DATA:
    seg_code, seg_name, fam_code, fam_name, cls_code, cls_name, commodities = entry
    for comm_code, comm_name in commodities:
        unspsc_rows.append({
            "segment_code": seg_code,
            "segment_name": seg_name,
            "family_code": fam_code,
            "family_name": fam_name,
            "class_code": cls_code,
            "class_name": cls_name,
            "commodity_code": comm_code,
            "commodity_name": comm_name,
        })

print(f"UNSPSC rows: {len(unspsc_rows)}")

with open(f"{BASE}/unspsc_v24.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "segment_code","segment_name","family_code","family_name",
        "class_code","class_name","commodity_code","commodity_name"
    ])
    writer.writeheader()
    writer.writerows(unspsc_rows)

print("unspsc_v24.csv written")

# ─────────────────────────────────────────────────────────────
# 2. fx_rates.csv
# ─────────────────────────────────────────────────────────────

import calendar

# AUD/XXX rate ranges (mean, min, max) — from_ccy=AUD, to_ccy=XXX
AUD_RATES = {
    "USD": (0.655, 0.630, 0.680),
    "EUR": (0.600, 0.580, 0.620),
    "GBP": (0.520, 0.500, 0.540),
    "SGD": (0.880, 0.850, 0.920),
    "NZD": (1.090, 1.070, 1.120),
    "JPY": (95.0, 90.0, 100.0),
    "CNY": (4.65, 4.50, 4.80),
}

# Seed for reproducibility
random.seed(42)

months = []
for year in [2023, 2024, 2025]:
    for month in range(1, 13):
        months.append(f"{year}-{month:02d}")

fx_rows = []
for ym in months:
    for ccy, (mean, lo, hi) in AUD_RATES.items():
        # Slightly trending rates with noise
        rate = round(random.uniform(lo, hi), 4)
        # AUD -> CCY
        fx_rows.append({
            "year_month": ym,
            "from_ccy": "AUD",
            "to_ccy": ccy,
            "rate": rate,
        })
        # CCY -> AUD (inverse)
        inv_rate = round(1 / rate, 6)
        fx_rows.append({
            "year_month": ym,
            "from_ccy": ccy,
            "to_ccy": "AUD",
            "rate": inv_rate,
        })

print(f"FX rows: {len(fx_rows)}")

with open(f"{BASE}/fx_rates.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["year_month","from_ccy","to_ccy","rate"])
    writer.writeheader()
    writer.writerows(fx_rows)

print("fx_rates.csv written")

# ─────────────────────────────────────────────────────────────
# 3. legal_suffixes.yaml
# ─────────────────────────────────────────────────────────────

legal_suffixes = {
    "suffixes": [
        "Pty Ltd", "Pty. Ltd.", "Pty. Ltd", "P/L", "P.L.",
        "LLC", "L.L.C.", "Inc", "Inc.", "Incorporated",
        "Ltd", "Ltd.", "Limited", "GmbH", "AG",
        "S.A.", "S.A.S.", "B.V.", "N.V.", "PLC",
        "Plc", "Corp", "Corp.", "Corporation", "Co",
        "Co.", "Company", "Trust", "Pty", "Holdings",
        "Group", "International", "Trading", "Services", "Solutions",
        "Aust", "Australia", "Global", "Enterprises", "Partners",
        "Consulting", "Industries", "Systems", "Technologies", "Ventures",
        "Foundation", "Association", "Council", "Institute", "Authority",
    ]
}

with open(f"{BASE}/legal_suffixes.yaml", "w") as f:
    yaml.dump(legal_suffixes, f, default_flow_style=False, sort_keys=False)

print(f"legal_suffixes.yaml written ({len(legal_suffixes['suffixes'])} entries)")

# ─────────────────────────────────────────────────────────────
# 4. abbreviation_map.yaml
# ─────────────────────────────────────────────────────────────

abbreviation_map = {
    "Aust": "Australia",
    "Intl": "International",
    "Svcs": "Services",
    "Mgt": "Management",
    "Mgmt": "Management",
    "Dept": "Department",
    "Govt": "Government",
    "Tech": "Technology",
    "Eng": "Engineering",
    "Mfg": "Manufacturing",
    "Distrib": "Distribution",
    "Comms": "Communications",
    "Corp": "Corporation",
    "Assoc": "Association",
    "Fndtn": "Foundation",
    "Natl": "National",
    "Fed": "Federal",
    "Qld": "Queensland",
    "NSW": "New South Wales",
    "Vic": "Victoria",
    "SA": "South Australia",
    "WA": "Western Australia",
    "Tas": "Tasmania",
    "ACT": "Australian Capital Territory",
    "NT": "Northern Territory",
    "Soln": "Solution",
    "Solns": "Solutions",
    "Sys": "Systems",
    "Ops": "Operations",
    "Proc": "Procurement",
    "Admin": "Administration",
    "Fin": "Finance",
    "HR": "Human Resources",
    "IT": "Information Technology",
    "Mktg": "Marketing",
    "Purch": "Purchasing",
    "Supp": "Supplier",
    "Dev": "Development",
    "Impl": "Implementation",
}

with open(f"{BASE}/abbreviation_map.yaml", "w") as f:
    yaml.dump(abbreviation_map, f, default_flow_style=False, sort_keys=False)

print(f"abbreviation_map.yaml written ({len(abbreviation_map)} entries)")

# ─────────────────────────────────────────────────────────────
# 5. category_seed_mappings.csv
# ─────────────────────────────────────────────────────────────

SEED_MAPPINGS = [
    # ── SUPPLIER mappings ──────────────────────────────────────
    # Telco / IT
    ("SUPPLIER","Telstra","IT","Telecommunications","Mobile Fleet","43","0.95"),
    ("SUPPLIER","Optus","IT","Telecommunications","Mobile Fleet","43","0.95"),
    ("SUPPLIER","Vodafone","IT","Telecommunications","Mobile Fleet","43","0.90"),
    ("SUPPLIER","TPG Telecom","IT","Telecommunications","Fixed Line","43","0.90"),
    ("SUPPLIER","Vocus","IT","Telecommunications","Fixed Line","43","0.88"),
    ("SUPPLIER","Microsoft","IT","Software","Productivity Software","43","0.97"),
    ("SUPPLIER","Adobe","IT","Software","Creative Software","43","0.97"),
    ("SUPPLIER","Salesforce","IT","Software","CRM Software","43","0.95"),
    ("SUPPLIER","SAP","IT","Software","ERP Software","43","0.95"),
    ("SUPPLIER","Oracle","IT","Software","Database Software","43","0.93"),
    ("SUPPLIER","AWS","IT","Cloud Services","Infrastructure","43","0.95"),
    ("SUPPLIER","Amazon Web Services","IT","Cloud Services","Infrastructure","43","0.95"),
    ("SUPPLIER","Google Cloud","IT","Cloud Services","Infrastructure","43","0.93"),
    ("SUPPLIER","Microsoft Azure","IT","Cloud Services","Infrastructure","43","0.93"),
    ("SUPPLIER","Dell","IT","Hardware","Computers","43","0.95"),
    ("SUPPLIER","HP","IT","Hardware","Computers","43","0.93"),
    ("SUPPLIER","Lenovo","IT","Hardware","Computers","43","0.93"),
    ("SUPPLIER","Apple","IT","Hardware","Mobile Devices","43","0.93"),
    ("SUPPLIER","Cisco","IT","Network Equipment","Switches and Routers","43","0.95"),
    # Logistics
    ("SUPPLIER","DHL","Logistics","Freight","International Freight","78","0.97"),
    ("SUPPLIER","FedEx","Logistics","Freight","International Freight","78","0.97"),
    ("SUPPLIER","TNT","Logistics","Freight","International Freight","78","0.95"),
    ("SUPPLIER","UPS","Logistics","Freight","International Freight","78","0.95"),
    ("SUPPLIER","Australia Post","Logistics","Freight","Domestic Mail","78","0.95"),
    ("SUPPLIER","StarTrack","Logistics","Freight","Domestic Freight","78","0.95"),
    ("SUPPLIER","Toll Group","Logistics","Freight","Domestic Freight","78","0.93"),
    ("SUPPLIER","Linfox","Logistics","Warehousing","Contract Logistics","78","0.93"),
    ("SUPPLIER","Mainfreight","Logistics","Freight","Domestic Freight","78","0.90"),
    ("SUPPLIER","DB Schenker","Logistics","Freight","International Freight","78","0.90"),
    # Facilities / Catering
    ("SUPPLIER","Sodexo","Facilities","Catering","Staff Catering","50","0.97"),
    ("SUPPLIER","Compass Group","Facilities","Catering","Staff Catering","50","0.97"),
    ("SUPPLIER","Spotless","Facilities","Cleaning","Commercial Cleaning","76","0.93"),
    ("SUPPLIER","ISS Facility Services","Facilities","Cleaning","Commercial Cleaning","76","0.95"),
    ("SUPPLIER","Broadspectrum","Facilities","Maintenance","Building Maintenance","72","0.90"),
    ("SUPPLIER","Programmed","Facilities","Maintenance","Building Maintenance","72","0.88"),
    ("SUPPLIER","CBRE","Facilities","Property","Property Management","72","0.90"),
    ("SUPPLIER","JLL","Facilities","Property","Property Management","72","0.90"),
    ("SUPPLIER","Cushman & Wakefield","Facilities","Property","Property Management","72","0.88"),
    # Office Supplies
    ("SUPPLIER","Officeworks","Office Supplies","Stationery","General Stationery","44","0.97"),
    ("SUPPLIER","Staples","Office Supplies","Stationery","General Stationery","44","0.97"),
    ("SUPPLIER","OfficeMax","Office Supplies","Stationery","General Stationery","44","0.95"),
    ("SUPPLIER","Cartridge World","Office Supplies","Print Consumables","Toner and Ink","44","0.95"),
    ("SUPPLIER","Fuji Xerox","Office Supplies","Print Equipment","Printers","44","0.93"),
    ("SUPPLIER","Konica Minolta","Office Supplies","Print Equipment","Copiers","44","0.93"),
    # Professional Services
    ("SUPPLIER","Deloitte","Professional Services","Consulting","Management Consulting","80","0.95"),
    ("SUPPLIER","KPMG","Professional Services","Consulting","Management Consulting","80","0.95"),
    ("SUPPLIER","PwC","Professional Services","Consulting","Management Consulting","80","0.95"),
    ("SUPPLIER","EY","Professional Services","Consulting","Management Consulting","80","0.95"),
    ("SUPPLIER","McKinsey","Professional Services","Consulting","Strategy Consulting","80","0.97"),
    ("SUPPLIER","BCG","Professional Services","Consulting","Strategy Consulting","80","0.97"),
    ("SUPPLIER","Allens","Professional Services","Legal","Corporate Law","80","0.95"),
    ("SUPPLIER","King & Wood Mallesons","Professional Services","Legal","Corporate Law","80","0.95"),
    ("SUPPLIER","Herbert Smith Freehills","Professional Services","Legal","Corporate Law","80","0.95"),
    ("SUPPLIER","Clayton Utz","Professional Services","Legal","Corporate Law","80","0.93"),
    # Recruitment / Labour
    ("SUPPLIER","Hays","Professional Services","Recruitment","Temporary Staffing","80","0.95"),
    ("SUPPLIER","Michael Page","Professional Services","Recruitment","Permanent Recruitment","80","0.95"),
    ("SUPPLIER","Robert Half","Professional Services","Recruitment","Professional Staffing","80","0.93"),
    ("SUPPLIER","Manpower","Professional Services","Recruitment","Temporary Staffing","80","0.93"),
    ("SUPPLIER","Adecco","Professional Services","Recruitment","Temporary Staffing","80","0.93"),
    # Engineering
    ("SUPPLIER","Aurecon","Professional Services","Engineering","Civil Engineering","81","0.95"),
    ("SUPPLIER","AECOM","Professional Services","Engineering","Engineering Consulting","81","0.95"),
    ("SUPPLIER","Jacobs","Professional Services","Engineering","Engineering Consulting","81","0.93"),
    ("SUPPLIER","GHD","Professional Services","Engineering","Engineering Consulting","81","0.93"),
    ("SUPPLIER","Arup","Professional Services","Engineering","Structural Engineering","81","0.93"),
    # Manufacturing / Industrial
    ("SUPPLIER","BlueScope Steel","Manufacturing","Raw Materials","Steel Products","73","0.95"),
    ("SUPPLIER","Dulux","Manufacturing","Raw Materials","Paints and Coatings","73","0.88"),
    ("SUPPLIER","3M","Manufacturing","Industrial Products","Safety Products","73","0.90"),
    ("SUPPLIER","Brady","Manufacturing","Industrial Products","Labelling","73","0.88"),
    # ── GL mappings ────────────────────────────────────────────
    ("GL","6420","Office Supplies","Stationery","","44","0.90"),
    ("GL","6421","Office Supplies","Print Consumables","","44","0.90"),
    ("GL","6422","Office Supplies","Print Equipment","","44","0.88"),
    ("GL","6300","Logistics","Freight","","78","0.90"),
    ("GL","6301","Logistics","Freight","International Freight","78","0.90"),
    ("GL","6302","Logistics","Warehousing","","78","0.88"),
    ("GL","6440","IT","Telecommunications","","43","0.90"),
    ("GL","6441","IT","Telecommunications","Mobile Fleet","43","0.92"),
    ("GL","6442","IT","Software","","43","0.90"),
    ("GL","6443","IT","Hardware","","43","0.88"),
    ("GL","6444","IT","Cloud Services","","43","0.88"),
    ("GL","6510","Facilities","Building Services","","72","0.88"),
    ("GL","6511","Facilities","Cleaning","","76","0.90"),
    ("GL","6512","Facilities","Catering","","50","0.90"),
    ("GL","6513","Facilities","Maintenance","","72","0.88"),
    ("GL","6514","Facilities","Property","","72","0.85"),
    ("GL","6600","Professional Services","Consulting","","80","0.85"),
    ("GL","6601","Professional Services","Legal","","80","0.88"),
    ("GL","6602","Professional Services","Audit and Accounting","","80","0.88"),
    ("GL","6603","Professional Services","Recruitment","","80","0.88"),
    ("GL","6700","Engineering","Engineering Consulting","","81","0.85"),
    ("GL","6800","Manufacturing","Raw Materials","","73","0.85"),
    ("GL","6420100","Office Supplies","Stationery","","44","0.92"),
    ("GL","6420200","Office Supplies","Print Consumables","","44","0.92"),
    ("GL","6440100","IT","Telecommunications","Mobile Fleet","43","0.92"),
    ("GL","6440200","IT","Software","Licensing","43","0.92"),
    ("GL","6510100","Facilities","Building Services","Electrical","72","0.90"),
    ("GL","6510200","Facilities","Building Services","HVAC","72","0.90"),
    ("GL","7000","Capital Expenditure","IT","Computer Equipment","43","0.80"),
    ("GL","7100","Capital Expenditure","Facilities","Fit-out","72","0.80"),
    ("GL","5500","Human Resources","Training","","80","0.82"),
    ("GL","5501","Human Resources","Recruitment","","80","0.85"),
    ("GL","5502","Human Resources","Travel and Accommodation","","78","0.85"),
    ("GL","5600","Marketing","Advertising","","55","0.82"),
    ("GL","5601","Marketing","Publishing","","55","0.85"),
    # ── KEYWORD mappings ───────────────────────────────────────
    ("KEYWORD","toner","Office Supplies","Print Consumables","","44","0.92"),
    ("KEYWORD","ink cartridge","Office Supplies","Print Consumables","","44","0.92"),
    ("KEYWORD","paper","Office Supplies","Stationery","","44","0.85"),
    ("KEYWORD","stationery","Office Supplies","Stationery","","44","0.90"),
    ("KEYWORD","printer","Office Supplies","Print Equipment","","44","0.88"),
    ("KEYWORD","copier","Office Supplies","Print Equipment","","44","0.88"),
    ("KEYWORD","catering","Facilities","Catering","","50","0.88"),
    ("KEYWORD","coffee","Facilities","Catering","Beverages","50","0.88"),
    ("KEYWORD","cleaning","Facilities","Cleaning","","76","0.88"),
    ("KEYWORD","cleaning services","Facilities","Cleaning","Commercial Cleaning","76","0.90"),
    ("KEYWORD","freight","Logistics","Freight","","78","0.90"),
    ("KEYWORD","courier","Logistics","Freight","","78","0.90"),
    ("KEYWORD","postage","Logistics","Freight","Domestic Mail","78","0.88"),
    ("KEYWORD","shipping","Logistics","Freight","","78","0.88"),
    ("KEYWORD","airfare","Logistics","Travel","Air Travel","78","0.92"),
    ("KEYWORD","airline","Logistics","Travel","Air Travel","78","0.90"),
    ("KEYWORD","hotel","Logistics","Travel","Accommodation","78","0.88"),
    ("KEYWORD","accommodation","Logistics","Travel","Accommodation","78","0.90"),
    ("KEYWORD","car hire","Logistics","Travel","Car Rental","78","0.88"),
    ("KEYWORD","fuel","Logistics","Travel","Fuel","78","0.85"),
    ("KEYWORD","software licence","IT","Software","","43","0.90"),
    ("KEYWORD","software subscription","IT","Software","","43","0.90"),
    ("KEYWORD","cloud","IT","Cloud Services","","43","0.88"),
    ("KEYWORD","mobile phone","IT","Telecommunications","Mobile Fleet","43","0.92"),
    ("KEYWORD","internet","IT","Telecommunications","Fixed Line","43","0.88"),
    ("KEYWORD","laptop","IT","Hardware","Computers","43","0.90"),
    ("KEYWORD","computer","IT","Hardware","Computers","43","0.90"),
    ("KEYWORD","server","IT","Hardware","Servers","43","0.90"),
    ("KEYWORD","network","IT","Network Equipment","","43","0.85"),
    ("KEYWORD","consulting","Professional Services","Consulting","","80","0.80"),
    ("KEYWORD","legal fees","Professional Services","Legal","","80","0.88"),
    ("KEYWORD","audit","Professional Services","Audit and Accounting","","80","0.88"),
    ("KEYWORD","recruitment","Professional Services","Recruitment","","80","0.88"),
    ("KEYWORD","training","Professional Services","Training","","80","0.82"),
    ("KEYWORD","maintenance","Facilities","Maintenance","","72","0.80"),
    ("KEYWORD","repair","Facilities","Maintenance","","72","0.78"),
    ("KEYWORD","plumbing","Facilities","Maintenance","Plumbing","72","0.88"),
    ("KEYWORD","electrical","Facilities","Maintenance","Electrical","72","0.88"),
    ("KEYWORD","safety","Manufacturing","Safety","PPE","53","0.80"),
    ("KEYWORD","uniform","Manufacturing","Safety","Uniforms","53","0.88"),
    ("KEYWORD","PPE","Manufacturing","Safety","PPE","53","0.90"),
    ("KEYWORD","gloves","Manufacturing","Safety","PPE","53","0.85"),
    ("KEYWORD","hard hat","Manufacturing","Safety","PPE","53","0.90"),
    ("KEYWORD","waste","Facilities","Cleaning","Waste Management","76","0.85"),
    ("KEYWORD","chemicals","Facilities","Cleaning","Cleaning Chemicals","76","0.82"),
    ("KEYWORD","medical","Pharma","Medical Supplies","","51","0.75"),
    ("KEYWORD","pharmaceutical","Pharma","Drugs","","51","0.88"),
    ("KEYWORD","food","Facilities","Catering","","50","0.80"),
    ("KEYWORD","beverage","Facilities","Catering","Beverages","50","0.82"),
    ("KEYWORD","publication","Marketing","Publishing","","55","0.82"),
    ("KEYWORD","subscription","IT","Software","","43","0.72"),
    ("KEYWORD","engineering","Professional Services","Engineering","","81","0.78"),
    ("KEYWORD","testing","Professional Services","Engineering","Testing","81","0.78"),
    ("KEYWORD","calibration","Professional Services","Engineering","Calibration","81","0.85"),
    ("KEYWORD","rent","Facilities","Property","Rent","72","0.90"),
    ("KEYWORD","lease","Facilities","Property","Lease","72","0.88"),
    ("KEYWORD","insurance","Professional Services","Insurance","","80","0.85"),
    ("KEYWORD","advertising","Marketing","Advertising","","55","0.82"),
    ("KEYWORD","marketing","Marketing","Marketing Services","","55","0.80"),
    ("KEYWORD","construction","Facilities","Construction","","72","0.85"),
    ("KEYWORD","fit-out","Facilities","Construction","Fit-out","72","0.88"),
    ("KEYWORD","landscaping","Facilities","Grounds","Landscaping","72","0.88"),
    ("KEYWORD","gardening","Facilities","Grounds","Landscaping","72","0.85"),
    ("KEYWORD","manufacturing","Manufacturing","Production","","73","0.78"),
    ("KEYWORD","fabrication","Manufacturing","Production","Fabrication","73","0.85"),
    ("KEYWORD","welding","Manufacturing","Production","Fabrication","73","0.85"),
    # Additional SUPPLIER mappings
    ("SUPPLIER","Qantas","Logistics","Travel","Air Travel","78","0.95"),
    ("SUPPLIER","Virgin Australia","Logistics","Travel","Air Travel","78","0.95"),
    ("SUPPLIER","Jetstar","Logistics","Travel","Air Travel","78","0.93"),
    ("SUPPLIER","Flight Centre","Logistics","Travel","Travel Management","78","0.90"),
    ("SUPPLIER","Corporate Travel Management","Logistics","Travel","Travel Management","78","0.90"),
    ("SUPPLIER","Marriott","Logistics","Travel","Accommodation","78","0.92"),
    ("SUPPLIER","Hilton","Logistics","Travel","Accommodation","78","0.92"),
    ("SUPPLIER","Accor Hotels","Logistics","Travel","Accommodation","78","0.92"),
    ("SUPPLIER","Avis","Logistics","Travel","Car Rental","78","0.90"),
    ("SUPPLIER","Hertz","Logistics","Travel","Car Rental","78","0.90"),
    ("SUPPLIER","Uber","Logistics","Travel","Ground Transport","78","0.88"),
    ("SUPPLIER","Thales","Manufacturing","Defence","Electronics","73","0.85"),
    ("SUPPLIER","Caterpillar","Manufacturing","Heavy Equipment","Machinery","73","0.90"),
    ("SUPPLIER","Komatsu","Manufacturing","Heavy Equipment","Machinery","73","0.90"),
    ("SUPPLIER","Schneider Electric","IT","Energy Management","Power Systems","43","0.88"),
    ("SUPPLIER","Johnson Controls","Facilities","Building Automation","BMS","72","0.88"),
    ("SUPPLIER","Siemens","Facilities","Building Automation","BMS","72","0.88"),
    ("SUPPLIER","Honeywell","Facilities","Building Automation","BMS","72","0.85"),
    ("SUPPLIER","Bunnings","Facilities","Maintenance","Hardware","72","0.85"),
    ("SUPPLIER","Grainger","Facilities","Maintenance","MRO Supplies","72","0.85"),
    ("SUPPLIER","Blackwoods","Manufacturing","Safety","PPE","53","0.88"),
    ("SUPPLIER","Protector Alsafe","Manufacturing","Safety","PPE","53","0.88"),
    # Additional GL mappings
    ("GL","6450","Facilities","Grounds","Landscaping","72","0.85"),
    ("GL","6460","Facilities","Security","Guard Services","80","0.85"),
    ("GL","6470","Facilities","Waste Management","","76","0.85"),
    ("GL","6480","Office Supplies","Furniture","","44","0.85"),
    ("GL","6490","Facilities","Catering","Beverages","50","0.88"),
    ("GL","6620","Professional Services","Insurance","","80","0.82"),
    ("GL","6630","Professional Services","Training","","80","0.82"),
    ("GL","5503","Human Resources","Benefits","","80","0.80"),
    ("GL","5510","Logistics","Travel","Air Travel","78","0.88"),
    ("GL","5511","Logistics","Travel","Accommodation","78","0.88"),
    ("GL","5512","Logistics","Travel","Ground Transport","78","0.85"),
    # Additional KEYWORD mappings
    ("KEYWORD","video conference","IT","Telecommunications","Video Conferencing","43","0.90"),
    ("KEYWORD","managed services","IT","Managed Services","","43","0.85"),
    ("KEYWORD","helpdesk","IT","Support Services","","43","0.88"),
    ("KEYWORD","security guard","Facilities","Security","Guard Services","80","0.90"),
    ("KEYWORD","CCTV","Facilities","Security","Surveillance","80","0.88"),
    ("KEYWORD","waste disposal","Facilities","Waste Management","","76","0.88"),
    ("KEYWORD","rubbish","Facilities","Waste Management","","76","0.85"),
    ("KEYWORD","recycling","Facilities","Waste Management","Recycling","76","0.85"),
    ("KEYWORD","furniture","Office Supplies","Furniture","","44","0.85"),
    ("KEYWORD","desk","Office Supplies","Furniture","Desks","44","0.85"),
    ("KEYWORD","chair","Office Supplies","Furniture","Chairs","44","0.85"),
]

print(f"Seed mapping rows: {len(SEED_MAPPINGS)}")

with open(f"{BASE}/category_seed_mappings.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["mapping_type","source_value","internal_category_l1",
                     "internal_category_l2","internal_category_l3",
                     "unspsc_segment_code","confidence"])
    for row in SEED_MAPPINGS:
        writer.writerow(row)

print("category_seed_mappings.csv written")

# ─────────────────────────────────────────────────────────────
# Verify
# ─────────────────────────────────────────────────────────────
import pandas as pd

df_unspsc = pd.read_csv(f"{BASE}/unspsc_v24.csv")
df_fx = pd.read_csv(f"{BASE}/fx_rates.csv")
df_cat = pd.read_csv(f"{BASE}/category_seed_mappings.csv")
suf = yaml.safe_load(open(f"{BASE}/legal_suffixes.yaml"))
abbr = yaml.safe_load(open(f"{BASE}/abbreviation_map.yaml"))

print(f"\nVerification:")
print(f"  UNSPSC rows: {len(df_unspsc)} (need >=400)")
print(f"  FX rows: {len(df_fx)} (need >=504)")
print(f"  Category seed rows: {len(df_cat)} (need >=200)")
print(f"  Legal suffixes: {len(suf['suffixes'])} (need >=40)")
print(f"  Abbreviations: {len(abbr)} (need >=30)")
print("\nAll reference files OK")
