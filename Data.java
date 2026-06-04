import java.io.File;
import java.io.FileNotFoundException;
import java.util.ArrayList;
import java.util.Scanner;

public class Data {
	
	/*
	 * Match.java is the "series" of either BO3 or BO5 game, it takes basic data
	 * like the match-up, map name, day of week, month, tournamentName...
	 * Rounds.java is an individual map's data
	 * RoundEvent.java is the list of rounds' data of a map
	 */
	
	static Match match;
	private static ArrayList<Match> arrMatch = new ArrayList<Match>();
	private static ArrayList<Integer> arr = new ArrayList<Integer>();
	private static Scanner file;
	private static String[] line;
	
	private static int counter;
	
	static ArrayList<Integer> roundUOAcqA = new ArrayList<Integer>();
	static ArrayList<Integer> roundUOAcqB = new ArrayList<Integer>();
	
	static ArrayList<Integer> roundnumAUA = new ArrayList<Integer>();
	static ArrayList<Integer> roundnumAUB = new ArrayList<Integer>();
	
	static ArrayList<Double> roundavgUPAA = new ArrayList<Double>();
	static ArrayList<Double> roundavgUPAB = new ArrayList<Double>();
	
	static ArrayList<Integer> roundteamEVA = new ArrayList<Integer>();
	static ArrayList<Integer> roundteamEVB = new ArrayList<Integer>();
	
	static ArrayList<Integer> wRound = new ArrayList<Integer>();
	
	static ArrayList<Double> am = new ArrayList<Double>(); 

	
	// static int momentum = 0;
	
	
	// static int sumtemp = 0;
	
	public static void main(String[] args) throws FileNotFoundException {	
		file = new Scanner(new File("VCT Data.csv"));
		int temp = 10;
		
		while(file.hasNextLine()) {
			counter=0;
			arr = new ArrayList<Integer>();
			
			for(int i = 0; i < temp; i++) {
				if(file.hasNextLine()) {
					
					//momentum = 0;
					
					//System.out.println(arr);
					
					setMap(file);
					counter++;
					
					//arrMatch.add(match);
				}else {
					break;
				}
				
				if(Character.isDigit(line[0].charAt(0))) {
					temp = Integer.parseInt(line[1].substring(1));
				}
				//arrMatch.add(match);
			}			
			
			
			for(int i = 0; i < 7; i++) {
				if(file.hasNextLine()) {
					file.nextLine();
				}
			}		
		}
		
		//for(Match m : arrMatch) {
		//	ArrayList<Rounds> round = m.getRound();
		//	
		//	for(Rounds r : round) {
		//		System.out.println(r.getRoundEventA().toString());
		//		System.out.println(r.getRoundEventB().toString());
		//	}
		//}
		
		/*
		System.out.println(roundUOAcqA + "\n" + roundUOAcqB + "\n" + roundnumAUA + "\n" + roundnumAUB + "\n" 
		+ roundavgUPAA + "\n" + roundavgUPAB + "\n" + roundteamEVA + "\n" + roundteamEVB + "\n" + wRound);
		
		System.out.println(roundUOAcqA.size());
		System.out.println(roundUOAcqB.size());
		
		System.out.println(roundnumAUA.size());
		System.out.println(roundnumAUB.size());
		
		System.out.println(roundavgUPAA.size());
		System.out.println(roundavgUPAB.size());
		
		System.out.println(roundteamEVA.size());
		System.out.println(roundteamEVB.size());
		
		System.out.println(wRound.size());
		*/
		
		ArrayList<Integer> uo = new ArrayList<Integer>();
		ArrayList<Integer> au = new ArrayList<Integer>();
		ArrayList<Double> up = new ArrayList<Double>();
		ArrayList<Integer> ev = new ArrayList<Integer>();		
		
		//System.out.println(wRound.size());
		
		//System.out.println(roundnumAUB.size());
		
		for(int i = 0; i < wRound.size(); i++) {
			//uo.add(roundUOAcqA.get(i)-roundUOAcqB.get(i));
			
			// int alteredAUA = (int) ((roundnumAUA.get(i)+Math.pow(roundnumAUA.get(i), 2))/2);
			// int alteredAUB = (int) ((roundnumAUB.get(i)+Math.pow(roundnumAUB.get(i), 2))/2);

			// int AUtemp = alteredAUA - alteredAUB;
			 int AUtemp = roundnumAUA.get(i)-roundnumAUB.get(i);
			au.add(AUtemp);
			
			// double alteredA = 10/(Math.pow(roundavgUPAA.get(i)-1, 2)+2);
			// double alteredB = 10/(Math.pow(roundavgUPAB.get(i)-1, 2)+2);
			// double UPAtemp = (double)Math.round((alteredA-alteredB)*100000d) / 100000d;
			
			 double UPAtemp =(double)Math.round((roundavgUPAA.get(i)-roundavgUPAB.get(i))*100000d) / 100000d;
			
			 up.add(UPAtemp);
			
			ev.add(roundteamEVA.get(i)-roundteamEVB.get(i));
		}
		// System.out.println(au + ",\n" + up + ",\n" + ev + ",\n" + am + ",\n" + wRound);
		System.out.println(au + ",\n" + up + ",\n" + ev + ",\n" + wRound);

		// System.out.println(uo.size());
		System.out.println(au.size());
		System.out.println(up.size());
		System.out.println(ev.size());
		
		System.out.println("am: " + am.size());
		
		System.out.println(wRound.size());
		
		
		int suc = 0;
		int tot = 0;
		
		for(int i = 0; i < wRound.size()-8;i++) {
			i+= (int)(Math.random()*7)+1;
			tot++;
			if((ev.get(i) < 0 && wRound.get(i) == 0) || (ev.get(i)>0 && wRound.get(i)==1)) {
				suc++;
			}else if(ev.get(i) == 0) {
				//System.out.println("hey");
				tot--;
			}else {
				
			}
		}
		System.out.println(suc);
		System.out.println(tot);
		System.out.println((double)suc/tot);
		
		
		//System.out.println(sumtemp);
	
	}

	private static void setMap(Scanner file) {
				
		// handles first line
		String[] temp = file.nextLine().trim().split(",");
		line = temp;
		Rounds roundA = new Rounds();
		Rounds roundB = new Rounds();
		RoundEvent roundEventA = new RoundEvent();
		RoundEvent roundEventB = new RoundEvent();
		
		if(Character.isDigit(temp[0].charAt(0))) {
			int mapNum = Integer.parseInt(temp[1].substring(1));
			
			if(mapNum == 2) {
				arr.add(Integer.parseInt(temp[2]));
				arr.add(Integer.parseInt(temp[3].substring(0, temp[3].length()-1)));
			}
			else if(mapNum == 3) {
				arr.add(Integer.parseInt(temp[2]));
				arr.add(Integer.parseInt(temp[3]));
				arr.add(Integer.parseInt(temp[4].substring(0, temp[4].length()-1)));
			}
			else if(mapNum == 4) {
				arr.add(Integer.parseInt(temp[2]));
				arr.add(Integer.parseInt(temp[3]));
				arr.add(Integer.parseInt(temp[4]));
				arr.add(Integer.parseInt(temp[5].substring(0, temp[5].length()-1)));
			}
			else if(mapNum == 5) {
				arr.add(Integer.parseInt(temp[2]));
				arr.add(Integer.parseInt(temp[3]));
				arr.add(Integer.parseInt(temp[4]));
				arr.add(Integer.parseInt(temp[5]));
				arr.add(Integer.parseInt(temp[6].substring(0, temp[6].length()-1)));
			}
			
			match = new Match();
			
			String[] temp3 = temp[0].trim().split("[0-9]+. ");
			String[] temp2 = temp3[1].trim().split(" \\| ");
			
			match.setMatchUp(temp2[0]);
			roundA.setMapNum(Integer.parseInt(""+temp2[1].charAt(temp2[1].length()-1)));
			roundA.setMapName(temp2[2]);
			roundB.setMapNum(Integer.parseInt(""+temp2[1].charAt(temp2[1].length()-1)));
			roundB.setMapName(temp2[2]);
		}else {
			String[] temp2 = temp[0].trim().split(" \\| ");
			roundA.setMapNum(Integer.parseInt(""+temp2[1].charAt(temp2[1].length()-1)));
			roundA.setMapName(temp2[2]);
			roundB.setMapNum(Integer.parseInt(""+temp2[1].charAt(temp2[1].length()-1)));
			roundB.setMapName(temp2[2]);
		}
		
		// System.out.println("h");
		
		// handles second line
		temp = file.nextLine().trim().split(",");
		
		match.setDayOfWeek(temp[0].substring(0));
		temp = temp[1].split(" ");
		
		match.setMonth(temp[1]);		
		match.setDay(Integer.parseInt(temp[2].substring(0, temp[2].length()-2)));
		
		if(temp[3].equals("12:00") && temp[4].equals("AM")) {
			match.setTime(0000);
		}else {
			if(temp[4].equals("AM")) {
				match.setTime(Integer.parseInt(temp[3].replaceAll(":", "")));
			}else {
				match.setTime(1200 + Integer.parseInt(temp[3].replaceAll(":", "")));
			}
		}
		
		// handles third line
		temp = file.nextLine().trim().split(","); 		
		double pVersion = Double.parseDouble(temp[0].replaceAll("Patch ", ""));
		match.setpVersion(pVersion);
		
		// handles fourth line
		temp = file.nextLine().trim().split(","); 
		match.setTournamentName(temp[0]);
		
		// fifth line (nothing)
		file.nextLine();
		
		// sixth line
		temp = file.nextLine().trim().split(",");
		
		roundA.sethBuy(Integer.parseInt(temp[3]));
		roundB.sethBuy(Integer.parseInt(temp[4]));
			
		// seventh line
		temp = file.nextLine().trim().split(",");
		roundA.setfBuy(Integer.parseInt(temp[3]));
		roundB.setfBuy(Integer.parseInt(temp[4]));
		
		// eighth line
		temp = file.nextLine().trim().split(",");
		roundA.seteBuy(Integer.parseInt(temp[3]));
		roundB.seteBuy(Integer.parseInt(temp[4]));
		
		// ninth line
		
		temp = file.nextLine().trim().split(",");
		
		/*
		if(Integer.parseInt(temp[3]) > 300) {
			System.out.println("outlier! " + Integer.parseInt(temp[3]));
		}
		roundA.setUPAcq(Integer.parseInt(temp[3]));
		
		ArrayList<Integer> roundUPAcq1 = new ArrayList<Integer>();
		
		//System.out.println(arr.get(counter));
		
		for(int i = 1; i < Math.min(arr.get(counter), 24); i++) {
			if(i == 12) {
				continue;
			}
			if(Integer.parseInt(temp[6+i]) > 15) {
				System.out.println("outlier! " + Integer.parseInt(temp[6+i]));
			}

			roundUPAcq1.add(Integer.parseInt(temp[6+i]));
		}
		roundEventA.setRoundUPAcq(roundUPAcq1);
		
		System.out.println("Nihao: " + roundEventA.toString());
		
		*/
		
		
		// tenth line
		temp = file.nextLine().trim().split(",");
		
		/*
		roundB.setUPAcq(Integer.parseInt(temp[4])); 
		
		if(Integer.parseInt(temp[4]) > 300) {
			System.out.println("outlier! " + Integer.parseInt(temp[4]));
		}
		
		ArrayList<Integer> roundUPAcq2 = new ArrayList<Integer>();
		
		for(int i = 1; i < Math.min(arr.get(counter), 24); i++) {
			if(i == 12) {
				continue;
			}
			if(Integer.parseInt(temp[6+i]) > 15) {
				System.out.println("outlier! " + Integer.parseInt(temp[6+i]));
			}
			roundUPAcq2.add(Integer.parseInt(temp[6+i]));
		}
		roundEventB.setRoundUPAcq(roundUPAcq2);
		
		System.out.println("Nihao: " + roundEventB.toString());
		
		*/
		
		// eleventh line
		temp = file.nextLine().trim().split(",");
		
		/*
		roundA.setUOAcq(Integer.parseInt(temp[3]));
	
		ArrayList<Integer> roundUOAcq1 = new ArrayList<Integer>();
		
		for(int i = 1; i < Math.min(arr.get(counter), 24); i++) {
			if(i == 12) {
				continue;
			}
			if(Integer.parseInt(temp[6+i]) > 3) {
				System.out.println("outlier! " + Integer.parseInt(temp[6+i]));
			}
			roundUOAcq1.add(Integer.parseInt(temp[6+i]));
		}
		roundEventA.setRoundUOAcq(roundUOAcq1);
		*/
		
		// twelfth line
		temp = file.nextLine().trim().split(",");
		
		/*
		roundB.setUOAcq(Integer.parseInt(temp[4]));

		ArrayList<Integer> roundUOAcq2 = new ArrayList<Integer>();
		
		for(int i = 1; i < Math.min(arr.get(counter), 24); i++) {
			if(i == 12) {
				continue;
			}
			if(Integer.parseInt(temp[6+i]) > 3) {
				System.out.println("outlier! " + Integer.parseInt(temp[6+i]));
			}
			roundUOAcq2.add(Integer.parseInt(temp[6+i]));
		}
		roundEventB.setRoundUOAcq(roundUOAcq2);
		*/
		
		// thirteenth
		temp = file.nextLine().trim().split(",");
		roundA.setMapWinPct(Double.parseDouble(temp[3].substring(0, temp[3].length()-1))/100);
		roundB.setMapWinPct(Double.parseDouble(temp[4].substring(0, temp[4].length()-1))/100);
		
		// fourteenth
		temp = file.nextLine().trim().split(",");
		roundA.setAtkWinPct(Double.parseDouble(temp[3].substring(0, temp[3].length()-1))/100);
		roundB.setAtkWinPct(Double.parseDouble(temp[4].substring(0, temp[4].length()-1))/100);

		// fifteenth
		temp = file.nextLine().trim().split(",");
		roundA.setDefWinPct(Double.parseDouble(temp[3].substring(0, temp[3].length()-1))/100);
		roundB.setDefWinPct(Double.parseDouble(temp[4].substring(0, temp[4].length()-1))/100);

		// sixteenth (nothing)
		file.nextLine();

		// seventeenth (nothing)
		file.nextLine();

		// eighteenth (nothing)
		file.nextLine();

		// nineteenth (nothing)
		file.nextLine();

		// 20
		temp = file.nextLine().trim().split(",");
		if(temp[2].equals("A")) {
			roundA.setwMap(1);
			roundB.setwMap(0);
		}else{
			roundA.setwMap(0);
			roundB.setwMap(1);
		}
		
		// 21 (nothing)
		file.nextLine();

		// 22
		temp = file.nextLine().trim().split(",");
	
		ArrayList<Integer> roundnumAU1 = new ArrayList<Integer>();
		
		for(int i = 1; i < Math.min(arr.get(counter), 24); i++) {
			if(i == 12) {
				continue;
			}
			//System.out.println("i: " + i );
			if(Integer.parseInt(temp[6+i]) > 5) {
				System.out.println("outlier! " + Integer.parseInt(temp[6+i]));
			}
			roundnumAU1.add(Integer.parseInt(temp[6+i]));
		}
		roundEventA.setRoundnumAU(roundnumAU1);
		
		// 23
		temp = file.nextLine().trim().split(",");
		
		ArrayList<Integer> roundnumAU2 = new ArrayList<Integer>();
		
		for(int i = 1; i < Math.min(arr.get(counter), 24); i++) {
			if(i == 12) {
				continue;
			}
			if(Integer.parseInt(temp[6+i]) > 5) {
				System.out.println("outlier! " + Integer.parseInt(temp[6+i]));
			}
			roundnumAU2.add(Integer.parseInt(temp[6+i]));
		}
		roundEventB.setRoundnumAU(roundnumAU2);

		// 24
		temp = file.nextLine().trim().split(",");

		ArrayList<Double> roundavgUPA1 = new ArrayList<Double>();
		
		for(int i = 1; i < Math.min(arr.get(counter), 24); i++) {
			if(i == 12) {
				continue;
			}
			if(Double.parseDouble(temp[6+i]) > 9) {
				System.out.println("outlier! " + Double.parseDouble(temp[6+i]));
			}
			roundavgUPA1.add(Double.parseDouble(temp[6+i]));
		}
		roundEventA.setRoundavgUPA(roundavgUPA1);
		
		// 25
		temp = file.nextLine().trim().split(",");
		
		ArrayList<Double> roundavgUPA2 = new ArrayList<Double>();
		
		for(int i = 1; i < Math.min(arr.get(counter), 24); i++) {
			if(i == 12) {
				continue;
			}
			if(Double.parseDouble(temp[6+i]) > 9) {
				System.out.println("outlier! " + Double.parseDouble(temp[6+i]));
			}
			roundavgUPA2.add(Double.parseDouble(temp[6+i]));
		}
		roundEventB.setRoundavgUPA(roundavgUPA2);
		
		// 26
		temp = file.nextLine().trim().split(",");

		ArrayList<Integer> roundteamEV1 = new ArrayList<Integer>();
		
		for(int i = 1; i < Math.min(arr.get(counter), 24); i++) {
			if(i == 12) {
				continue;
			}
			if(Integer.parseInt(temp[6+i]) > 40000 || Integer.parseInt(temp[6+i]) % 50 != 0) {
				System.out.println("outlier! " + Integer.parseInt(temp[6+i]));
			}
			roundteamEV1.add(Integer.parseInt(temp[6+i]));
		}
		roundEventA.setRoundteamEV(roundteamEV1);
		
		// 27
		temp = file.nextLine().trim().split(",");

		ArrayList<Integer> roundteamEV2 = new ArrayList<Integer>();
		
		for(int i = 1; i < Math.min(arr.get(counter), 24); i++) {
			if(i == 12) {
				continue;
			}
			if(Integer.parseInt(temp[6+i]) > 40000 || Integer.parseInt(temp[6+i]) % 50 != 0) {
				System.out.println("outlier! " + Integer.parseInt(temp[6+i]));
			}
			roundteamEV2.add(Integer.parseInt(temp[6+i]));
		}
		roundEventB.setRoundteamEV(roundteamEV2);
		
		// 28
		temp = file.nextLine().trim().split(",");

		ArrayList<Integer> wRound1 = new ArrayList<Integer>();
		ArrayList<Integer> wRound2 = new ArrayList<Integer>();

		for(int i = 1; i < Math.min(arr.get(counter), 24); i++) {
			
			//System.out.println("momentu: " + momentum);
			if(i == 12) {
				continue;
			}
			
			//System.out.println("i: " + i);
			if(temp[6+i].equals("A")) {
				wRound1.add(1);
				wRound2.add(0);
				
				/* old momentum logic
				if(momentum != 0) {
					double momentumLog = (momentum/Math.abs(momentum)) * Math.log(Math.abs(momentum)+1);
					am.add((int)(momentumLog * 100000) / 100000.0);
				}else {
					am.add(0.0);
				}
				
				if(momentum < 0) {
					momentum = 0;
				}
				momentum++;
				*/
				
			}else if(temp[6+i].equals("B")){
				wRound1.add(0);
				wRound2.add(1);
				
				/*
				if(momentum != 0) {
					double momentumLog = (momentum/Math.abs(momentum)) * Math.log(Math.abs(momentum)+1);
					am.add((int)(momentumLog * 100000) / 100000.0);
				}else {
					am.add(0.0);
				}
			
				if(momentum > 0) {
					momentum = 0;
				}
				momentum--;
				*/
				
			}else {
				System.out.println("HELSIDOASID");
			}
		}
		
		// alternate winRounds
		ArrayList<Integer> winners = new ArrayList<Integer>();
		
		for(int i = 0; i < arr.get(counter); i++) {
			
			if(temp[6+i].equals("A")) {
				winners.add(1);
		
			}else{
				winners.add(0);
			}
		}
		ArrayList<Double> tempMomentumArray = calculateMomentum(winners, 0.1);
		
		// System.out.println("momentum array: " + tempMomentumArray);
		// System.out.println("What is this: " + -2.0 * Math.exp(0));
		
		for(int i = 1; i < Math.min(tempMomentumArray.size()-1, 24); i++) {
			if(i==13) {
				continue;
			}
			am.add(tempMomentumArray.get(i));
		}
		
		roundEventA.setwRound(wRound1);
		roundEventB.setwRound(wRound2);

		// summary add		
		roundA.addRoundEventA(roundEventA);
		roundB.addRoundEventB(roundEventB);
		
		match.setRoundA(roundA);
		match.setRoundB(roundB);
		
		arrMatch.add(match);
		
		//for(int n : match.getRoundA().getRoundEventA().getRoundUOAcq()) {
		//	roundUOAcqA.add(n);
		//}
		//for(int n : match.getRoundB().getRoundEventB().getRoundUOAcq()) {
		//	roundUOAcqB.add(n);
		//}
		
		for(int n : match.getRoundA().getRoundEventA().getRoundnumAU()) {
			roundnumAUA.add(n);
		}
		for(int n : match.getRoundB().getRoundEventB().getRoundnumAU()) {
			roundnumAUB.add(n);
		}
		
		for(double n : match.getRoundA().getRoundEventA().getRoundavgUPA()) {
			roundavgUPAA.add(n);
		}
		for(double n : match.getRoundB().getRoundEventB().getRoundavgUPA()) {
			roundavgUPAB.add(n);
		}
		
		for(int n : match.getRoundA().getRoundEventA().getRoundteamEV()) {
			roundteamEVA.add(n);
		}
		for(int n : match.getRoundB().getRoundEventB().getRoundteamEV()) {
			roundteamEVB.add(n);
		}
		
		for(int n : match.getRoundA().getRoundEventA().getwRound()) {
			wRound.add(n);
		}
		
		// 29 (nothing)
		file.nextLine();

		// 30 (nothing)
		file.nextLine();

		// 31 (nothing)
		file.nextLine();

		// 32 (nothing)
		file.nextLine();

		// 33 (nothing)
		if(file.hasNextLine()) {
			file.nextLine();
		}
	}

	private static ArrayList<Double> calculateMomentum(ArrayList<Integer> winners, double decayRate) {
		
		double momentum = 0.0;
		ArrayList<Double> momentumHistory = new ArrayList<Double>();
		int consecutiveWins = 0;
		int previousWinner = -1;
		
		momentumHistory.add(0.0);
		
		for(int i = 0; i < winners.size(); i++) {
			int n = winners.get(i);
			
			if(n == 1) {
				momentum+=0.2;
				
				if(previousWinner == 1) {
					consecutiveWins++;
				}else if(previousWinner == 0) {
					consecutiveWins = 1;
				}
			}
			else if(n == 0) {
				momentum-=0.2;
				
				if(previousWinner == 0) {
					consecutiveWins--;
				}else if(previousWinner == 1) {
					consecutiveWins=-1;
				}
			}
			
			if(consecutiveWins > 1) {
				momentum += 0.1 * consecutiveWins;
			}else if(consecutiveWins < -1) {
				momentum -= 0.1 * Math.abs(consecutiveWins);
			}
			
			// comeback
			if(previousWinner != n && previousWinner != -1) {
				if(n == 1) {
					momentum += 0.3;
				}
				else if(n == 0) {
					momentum -= 0.3;
				}
			}
			
			previousWinner = n;
			
			double weight = Math.exp(-decayRate * Math.abs(consecutiveWins));
			
			// System.out.println("weight: " + consecutiveWins);
			
			momentum *= weight;
			
			// System.out.println("point0: "+ momentum);
			
			momentum = Math.max(-2.0, Math.min(2.0, momentum));
			
			momentum = (double)Math.round(momentum*100000d) / 100000d;
			
			// System.out.println("point: " + momentum);

			momentumHistory.add(momentum);
		}
		
		return momentumHistory;
	}
}
