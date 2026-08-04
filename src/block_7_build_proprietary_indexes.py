#!/usr/bin/env python3
import json, math, os, sqlite3
from pathlib import Path

DB = os.getenv('DATABASE_PATH', 'data/database-fantacalcio.sqlite')
METHOD = 'block7-v1'


def clamp(v):
    if v is None: return None
    return max(0, min(100, int(round(v))))


def safe_div(a, b):
    return (a / b) if a is not None and b not in (None, 0) else None


def zscores(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    if len(vals) < 2:
        return {r['player_id']: 50 for r in rows}
    mean = sum(vals) / len(vals)
    sd = math.sqrt(sum((x-mean)**2 for x in vals) / len(vals)) or 1
    return {r['player_id']: clamp(50 + 15*((r.get(key, mean)-mean)/sd)) for r in rows}


def main():
    db = Path(DB)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(Path('migrations/007_block_7_proprietary_indexes.sql').read_text())

    seasons = conn.execute('SELECT season_id FROM seasons').fetchall()
    total = 0
    for s in seasons:
        sid = s['season_id']
        q = '''
        SELECT pss.player_id, pss.club_id, pss.minutes, pss.appearances, pss.starts,
               pss.goals, pss.assists, pss.goals_per90, pss.assists_per90,
               pss.yellow_cards, pss.red_cards, pss.clean_sheets,
               fs.average_rating AS avg_rating, fs.fantasy_average, fs.auction_value_index,
               fs.reliability_index AS fantasy_reliability,
               am.attacking_involvement_index AS offensive_involvement_index,
               am.chance_creation_index,
               am.progression_index AS ball_progression_index,
               am.pressing_index AS pressure_contribution_index,
               av.availability_pct, av.injury_risk_index
        FROM player_season_stats pss
        LEFT JOIN fantasy_player_season fs
          ON fs.player_id=pss.player_id AND fs.season_id=pss.season_id AND fs.club_id=pss.club_id
        LEFT JOIN player_advanced_season_metrics am
          ON am.player_id=pss.player_id AND am.season_id=pss.season_id AND am.club_id=pss.club_id
        LEFT JOIN player_availability av
          ON av.player_id=pss.player_id AND av.season_id=pss.season_id AND av.club_id=pss.club_id
        WHERE pss.season_id=?
        '''
        rows = [dict(r) for r in conn.execute(q, (sid,)).fetchall()]
        if not rows: continue
        g90 = zscores(rows, 'goals_per90')
        a90 = zscores(rows, 'assists_per90')
        mins = zscores(rows, 'minutes')
        rating = zscores(rows, 'avg_rating')

        for r in rows:
            apps = r.get('appearances') or 0
            starts = r.get('starts') or 0
            minutes = r.get('minutes') or 0
            start_rate = safe_div(starts, apps) or 0
            cards = (r.get('yellow_cards') or 0) + 2*(r.get('red_cards') or 0)
            malus = clamp(100 - min(100, cards*7))
            reliability = r.get('fantasy_reliability') or clamp(0.45*mins[r['player_id']] + 35*start_rate + min(20, apps))
            continuity = clamp(0.55*mins[r['player_id']] + 45*start_rate)
            rotation = clamp(100 - continuity)
            injury = r.get('injury_risk_index')
            bonus = clamp(0.45*g90[r['player_id']] + 0.35*a90[r['player_id']] + 0.20*(r.get('chance_creation_index') or 50))
            form = clamp(0.55*rating[r['player_id']] + 0.25*bonus + 0.20*reliability)
            auction = r.get('auction_value_index') or clamp(0.35*bonus + 0.25*continuity + 0.20*form + 0.20*(r.get('offensive_involvement_index') or 50))
            tactical = clamp(0.35*(r.get('ball_progression_index') or 50) + 0.30*(r.get('pressure_contribution_index') or 50) + 0.35*reliability)
            creativity = clamp(0.55*(r.get('chance_creation_index') or 50) + 0.25*a90[r['player_id']] + 0.20*(r.get('ball_progression_index') or 50))
            intensity = clamp(0.60*(r.get('pressure_contribution_index') or 50) + 0.40*continuity)
            completeness = clamp((bonus + tactical + creativity + intensity + reliability)/5)
            potential = clamp(0.35*form + 0.25*bonus + 0.20*continuity + 0.20*completeness)
            coverage_fields = ['minutes','appearances','goals_per90','assists_per90','avg_rating','fantasy_average','offensive_involvement_index','availability_pct']
            coverage = round(100*sum(r.get(k) is not None for k in coverage_fields)/len(coverage_fields), 1)
            confidence = round(coverage/100, 3)

            vals = (r['player_id'], sid, r['club_id'], form, reliability, continuity, rotation,
                    injury, None, None, None, bonus, 100-malus, auction, potential,
                    tactical, None, creativity, intensity, completeness, confidence, coverage, METHOD)
            conn.execute('''
              INSERT INTO proprietary_player_indexes(
                player_id,season_id,club_id,form_index,reliability_index,continuity_index,
                rotation_risk,injury_risk,home_performance_index,away_performance_index,
                big_match_index,bonus_index,malus_risk,auction_value_index,
                potential_performance_index,tactical_intelligence,adaptability,creativity,
                intensity,completeness,confidence,coverage_pct,methodology_version)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(player_id,season_id,club_id,methodology_version) DO UPDATE SET
                form_index=excluded.form_index,reliability_index=excluded.reliability_index,
                continuity_index=excluded.continuity_index,rotation_risk=excluded.rotation_risk,
                injury_risk=excluded.injury_risk,bonus_index=excluded.bonus_index,
                malus_risk=excluded.malus_risk,auction_value_index=excluded.auction_value_index,
                potential_performance_index=excluded.potential_performance_index,
                tactical_intelligence=excluded.tactical_intelligence,creativity=excluded.creativity,
                intensity=excluded.intensity,completeness=excluded.completeness,
                confidence=excluded.confidence,coverage_pct=excluded.coverage_pct,
                generated_at=CURRENT_TIMESTAMP
            ''', vals)
            total += 1

        feats = conn.execute('''SELECT player_id, form_index,reliability_index,continuity_index,
            bonus_index,malus_risk,auction_value_index,tactical_intelligence,creativity,intensity,
            completeness FROM proprietary_player_indexes WHERE season_id=? AND methodology_version=?''',
            (sid, METHOD)).fetchall()
        feats = [dict(x) for x in feats]
        keys = ['form_index','reliability_index','continuity_index','bonus_index','malus_risk',
                'auction_value_index','tactical_intelligence','creativity','intensity','completeness']
        for a in feats:
            distances=[]
            for b in feats:
                if a['player_id']==b['player_id']: continue
                pairs=[(a[k],b[k]) for k in keys if a[k] is not None and b[k] is not None]
                if len(pairs)<4: continue
                dist=math.sqrt(sum((x-y)**2 for x,y in pairs)/len(pairs))
                sim=max(0,100-dist)
                distances.append((sim,b['player_id'],100*len(pairs)/len(keys)))
            distances.sort(reverse=True)
            for rank,(sim,pid,cov) in enumerate(distances[:20],1):
                conn.execute('''INSERT INTO player_similarity(player_id,similar_player_id,season_id,rank,
                    similarity_score,feature_coverage_pct,methodology_version)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(player_id,similar_player_id,season_id,methodology_version) DO UPDATE SET
                    rank=excluded.rank, similarity_score=excluded.similarity_score,
                    feature_coverage_pct=excluded.feature_coverage_pct, generated_at=CURRENT_TIMESTAMP''',
                    (a['player_id'],pid,sid,rank,round(sim,3),round(cov,1),METHOD))

    conn.commit()
    report = {
      'methodology_version': METHOD,
      'index_rows': conn.execute('SELECT COUNT(*) FROM proprietary_player_indexes WHERE methodology_version=?',(METHOD,)).fetchone()[0],
      'similarity_rows': conn.execute('SELECT COUNT(*) FROM player_similarity WHERE methodology_version=?',(METHOD,)).fetchone()[0],
      'average_coverage_pct': conn.execute('SELECT ROUND(AVG(coverage_pct),2) FROM proprietary_player_indexes WHERE methodology_version=?',(METHOD,)).fetchone()[0]
    }
    Path('reports').mkdir(exist_ok=True)
    Path('reports/block_7_coverage_report.json').write_text(json.dumps(report,indent=2), encoding='utf-8')
    conn.close()
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
