import java.sql.*;
import java.util.Random;

/**
 * F-17 minimal repro: kwdb server crashes when batch-inserting into a
 * time-series table with 2+ rtags (one varchar + others) + many data cols.
 *
 * Tables: t_2rtag (1 ptag + 1 rtag_varchar + 1 rtag_smallint) and
 *        t_3rtag (1 ptag + 3 rtag_smallint) — match shig fixture shape.
 *
 * Symptom (kwdb/kwdb:latest): batch insert errors out with EOFException /
 *                             server exit; rtag_varchar_1 set to "".
 * Symptom (kwdb-x86_64-master-dbg): server segfault on restart in
 *                                   MMapTagColumnTable::push_back.
 *
 * Run:
 *   docker run -d --name kaiwudb-smoke -p 26257:26257 \
 *     kwdb/kwdb:latest /kaiwudb/bin/kwbase start-single-node \
 *     --insecure --listen-addr=0.0.0.0:26257
 *   javac F17Repro.java && \
 *   java -cp .:/path/to/kaiwudb-jdbc-3.2.0.jar F17Repro
 */
public class F17Repro {
    public static void main(String[] args) throws Exception {
        String url = "jdbc:kaiwudb://127.0.0.1:26257/defaultdb";
        Class.forName("com.kaiwudb.Driver");

        // Setup (autoCommit — TS DDL requires implicit txn)
        try (Connection setup = DriverManager.getConnection(url, "root", "")) {
            try (Statement st = setup.createStatement()) {
                st.execute("drop database if exists f17_repro cascade");
                st.execute("create ts database f17_repro");
                st.execute("use f17_repro");
                // 30 float4 + 16 int + 2 varchar + 1 smallint = 49 data cols
                // + 1 ptag + 2 rtag = matches shig t_electmeter shape
                st.execute(
                    "create table t_2rtag (\n" +
                    "  ts timestamp not null,\n" +
                    "  c1 float4, c2 float4, c3 float4, c4 float4, c5 float4,\n" +
                    "  c6 float4, c7 float4, c8 float4, c9 float4, c10 float4,\n" +
                    "  c11 float4, c12 float4, c13 float4, c14 float4, c15 float4,\n" +
                    "  c16 float4, c17 float4, c18 float4, c19 float4, c20 float4,\n" +
                    "  c21 float4, c22 float4, c23 float4, c24 float4, c25 float4,\n" +
                    "  c26 float4, c27 float4, c28 float4, c29 float4, c30 float4,\n" +
                    "  i1 int, i2 int, i3 int, i4 int, i5 int,\n" +
                    "  i6 int, i7 int, i8 int, i9 int, i10 int,\n" +
                    "  i11 int, i12 int, i13 int, i14 int, i15 int, i16 int,\n" +
                    "  v1 varchar(64), v2 varchar(64), sm1 smallint\n" +
                    ") tags (\n" +
                    "  ptag_varchar_1 varchar(32) not null,\n" +
                    "  rtag_varchar_1 varchar(64) not null,\n" +
                    "  rtag_smallint_1 smallint not null\n" +
                    ") primary tags(ptag_varchar_1)");
                // 3 rtag (all smallint) — t_cnc shape
                st.execute(
                    "create table t_3rtag (\n" +
                    "  ts timestamp not null,\n" +
                    "  c1 int\n" +
                    ") tags (\n" +
                    "  ptag_varchar_1 varchar(32) not null,\n" +
                    "  rtag_smallint_1 smallint not null,\n" +
                    "  rtag_smallint_2 smallint not null,\n" +
                    "  rtag_smallint_3 smallint not null\n" +
                    ") primary tags(ptag_varchar_1)");
            }
        }

        Random rng = new Random(42);

        // Insert into t_2rtag
        try (Connection conn = DriverManager.getConnection(url, "root", "")) {
            conn.setAutoCommit(false);
            conn.createStatement().execute("use f17_repro");
            String sql = "insert into t_2rtag (ts, c1, c2, c3, c4, c5, c6, c7, c8, c9, c10,\n" +
                "  c11, c12, c13, c14, c15, c16, c17, c18, c19, c20,\n" +
                "  c21, c22, c23, c24, c25, c26, c27, c28, c29, c30,\n" +
                "  i1, i2, i3, i4, i5, i6, i7, i8, i9, i10,\n" +
                "  i11, i12, i13, i14, i15, i16,\n" +
                "  v1, v2, sm1, ptag_varchar_1, rtag_varchar_1, rtag_smallint_1)\n" +
                "values (?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,?,?, ?,?,?)";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                for (int batch = 0; batch < 50; batch++) {
                    for (int i = 0; i < 50; i++) {
                        int idx = 1;
                        ps.setTimestamp(idx++, new Timestamp(System.currentTimeMillis() + (batch * 50 + i) * 1000L));
                        for (int c = 1; c <= 30; c++) ps.setFloat(idx++, rng.nextFloat() * 100);
                        for (int c = 1; c <= 16; c++) ps.setInt(idx++, rng.nextInt(1000));
                        ps.setString(idx++, "V" + rng.nextInt(2));
                        ps.setString(idx++, "V" + rng.nextInt(2));
                        ps.setLong(idx++, rng.nextInt(100));
                        ps.setString(idx++, "device_" + (1 + rng.nextInt(20)));
                        ps.setString(idx++, "op_group_" + (1 + rng.nextInt(4)));  // rtag varchar
                        ps.setLong(idx++, (1 + rng.nextInt(100)));                // rtag smallint
                        ps.addBatch();
                    }
                }
                System.out.println("Executing t_2rtag batch...");
                int[] result = ps.executeBatch();
                System.out.println("t_2rtag: " + result.length + " rows");
            }
            conn.commit();
        }

        // Insert into t_3rtag
        try (Connection conn = DriverManager.getConnection(url, "root", "")) {
            conn.setAutoCommit(false);
            conn.createStatement().execute("use f17_repro");
            String sql = "insert into t_3rtag (ts, c1, ptag_varchar_1, rtag_smallint_1, rtag_smallint_2, rtag_smallint_3) values (?, ?, ?, ?, ?, ?)";
            try (PreparedStatement ps = conn.prepareStatement(sql)) {
                for (int batch = 0; batch < 50; batch++) {
                    for (int i = 0; i < 50; i++) {
                        ps.setTimestamp(1, new Timestamp(System.currentTimeMillis() + (batch * 50 + i) * 1000L));
                        ps.setInt(2, batch * 100 + i);
                        ps.setString(3, "device_" + (1 + rng.nextInt(20)));
                        ps.setLong(4, 1 + rng.nextInt(4));    // sub_company_id
                        ps.setLong(5, 1 + rng.nextInt(20));   // factory_id
                        ps.setLong(6, 1 + rng.nextInt(100));  // workshop_id
                        ps.addBatch();
                    }
                }
                System.out.println("Executing t_3rtag batch...");
                int[] result = ps.executeBatch();
                System.out.println("t_3rtag: " + result.length + " rows");
            }
            conn.commit();
        }
        System.out.println("OK");
    }
}
